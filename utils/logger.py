"""
Enhanced Logging System with Replay Functionality
Provides structured logging, signal replay, and audit trails.
"""

import logging
import logging.handlers
import json
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from pathlib import Path
import gzip
import pickle
from dataclasses import dataclass, asdict
import threading
import queue
import time

from utils.helpers import format_currency, format_percentage
from strategy.rsi_psar_engulfing import TradingSignal


@dataclass
class LogEntry:
    """Structured log entry."""
    timestamp: datetime
    level: str
    component: str
    message: str
    data: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'level': self.level,
            'component': self.component,
            'message': self.message,
            'data': self.data,
            'session_id': self.session_id
        }


@dataclass
class SignalSnapshot:
    """Complete snapshot for signal replay."""
    timestamp: datetime
    ticker: str
    market_data: Dict[str, Any]  # OHLCV + indicators
    signal: Optional[TradingSignal]
    portfolio_state: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'ticker': self.ticker,
            'market_data': self.market_data,
            'signal': asdict(self.signal) if self.signal else None,
            'portfolio_state': self.portfolio_state
        }


class StructuredLogger:
    """Enhanced logger with structured logging and replay capabilities."""
    
    def __init__(self, config: Dict[str, Any], session_id: str = None):
        """
        Initialize structured logger.
        
        Args:
            config: Logging configuration
            session_id: Unique session identifier
        """
        self.config = config
        self.session_id = session_id or datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Setup log directories
        self.log_dir = Path(config.get('logging', {}).get('log_dir', 'log'))
        self.log_dir.mkdir(exist_ok=True)
        
        (self.log_dir / 'signals').mkdir(exist_ok=True)
        (self.log_dir / 'replay').mkdir(exist_ok=True)
        (self.log_dir / 'audit').mkdir(exist_ok=True)
        
        # Initialize loggers
        self._setup_loggers()
        
        # Async logging queue
        self.log_queue = queue.Queue(maxsize=1000)
        self.log_thread = None
        self.stop_logging = threading.Event()
        
        # Replay storage
        self.snapshots: List[SignalSnapshot] = []
        self.max_snapshots = config.get('logging', {}).get('max_snapshots', 1000)
    
    def _setup_loggers(self):
        """Setup different types of loggers."""
        log_config = self.config.get('logging', {})
        
        # Main application logger
        self.main_logger = logging.getLogger('realtime_alert.main')
        self.main_logger.setLevel(getattr(logging, log_config.get('level', 'INFO')))
        
        # Setup handlers
        self._setup_file_handlers()
        self._setup_console_handler()
        
        # Signal-specific logger
        self.signal_logger = logging.getLogger('realtime_alert.signals')
        self.signal_logger.setLevel(logging.INFO)
        
        # Audit logger
        self.audit_logger = logging.getLogger('realtime_alert.audit')
        self.audit_logger.setLevel(logging.INFO)
        
        # Performance logger
        self.perf_logger = logging.getLogger('realtime_alert.performance')
        self.perf_logger.setLevel(logging.INFO)
    
    def _setup_file_handlers(self):
        """Setup rotating file handlers."""
        log_config = self.config.get('logging', {})
        max_bytes = self._parse_size(log_config.get('max_file_size', '10MB'))
        backup_count = log_config.get('backup_count', 5)
        
        # Main log handler
        main_handler = logging.handlers.RotatingFileHandler(
            self.log_dir / f'main_{self.session_id}.log',
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        main_handler.setFormatter(self._get_formatter())
        self.main_logger.addHandler(main_handler)
        
        # Signals log handler
        signals_handler = logging.handlers.RotatingFileHandler(
            self.log_dir / 'signals' / f'signals_{self.session_id}.log',
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        signals_handler.setFormatter(self._get_formatter('signals'))
        self.signal_logger.addHandler(signals_handler)
        
        # Audit log handler
        audit_handler = logging.handlers.RotatingFileHandler(
            self.log_dir / 'audit' / f'audit_{self.session_id}.log',
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        audit_handler.setFormatter(self._get_formatter('audit'))
        self.audit_logger.addHandler(audit_handler)
        
        # Performance log handler
        perf_handler = logging.handlers.RotatingFileHandler(
            self.log_dir / f'performance_{self.session_id}.log',
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        perf_handler.setFormatter(self._get_formatter())
        self.perf_logger.addHandler(perf_handler)
    
    def _setup_console_handler(self):
        """Setup console handler."""
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(self._get_formatter())
        
        # Add to main logger only
        self.main_logger.addHandler(console_handler)
    
    def _get_formatter(self, logger_type: str = 'main') -> logging.Formatter:
        """Get formatter for specific logger type."""
        if logger_type == 'signals':
            return logging.Formatter(
                '%(asctime)s | %(levelname)s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        elif logger_type == 'audit':
            return logging.Formatter(
                '%(asctime)s | %(levelname)s | %(funcName)s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        else:
            return logging.Formatter(
                '%(asctime)s | %(name)s | %(levelname)s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
    
    def _parse_size(self, size_str: str) -> int:
        """Parse size string like '10MB' to bytes."""
        size_str = size_str.upper()
        if size_str.endswith('KB'):
            return int(size_str[:-2]) * 1024
        elif size_str.endswith('MB'):
            return int(size_str[:-2]) * 1024 * 1024
        elif size_str.endswith('GB'):
            return int(size_str[:-2]) * 1024 * 1024 * 1024
        else:
            return int(size_str)
    
    def start_async_logging(self):
        """Start asynchronous logging thread."""
        if self.log_thread is None:
            self.log_thread = threading.Thread(target=self._log_worker, daemon=True)
            self.log_thread.start()
    
    def stop_async_logging(self):
        """Stop asynchronous logging thread."""
        self.stop_logging.set()
        if self.log_thread:
            self.log_thread.join(timeout=5)
    
    def _log_worker(self):
        """Worker thread for asynchronous logging."""
        while not self.stop_logging.is_set():
            try:
                # Get log entry with timeout
                log_entry = self.log_queue.get(timeout=1)
                
                # Process log entry
                self._write_log_entry(log_entry)
                
                self.log_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                # Fallback logging to console
                print(f"Logging error: {e}")
    
    def _write_log_entry(self, entry: LogEntry):
        """Write log entry to appropriate logger."""
        logger_map = {
            'main': self.main_logger,
            'signals': self.signal_logger,
            'audit': self.audit_logger,
            'performance': self.perf_logger
        }
        
        logger = logger_map.get(entry.component, self.main_logger)
        level_map = {
            'DEBUG': logger.debug,
            'INFO': logger.info,
            'WARNING': logger.warning,
            'ERROR': logger.error,
            'CRITICAL': logger.critical
        }
        
        log_func = level_map.get(entry.level, logger.info)
        
        # Format message with data if present
        message = entry.message
        if entry.data:
            message += f" | Data: {json.dumps(entry.data, default=str)}"
        
        log_func(message)
    
    def log(self, level: str, component: str, message: str, 
           data: Optional[Dict[str, Any]] = None):
        """
        Log message with structured data.
        
        Args:
            level: Log level
            component: Component name
            message: Log message
            data: Additional structured data
        """
        entry = LogEntry(
            timestamp=datetime.now(),
            level=level,
            component=component,
            message=message,
            data=data,
            session_id=self.session_id
        )
        
        try:
            self.log_queue.put_nowait(entry)
        except queue.Full:
            # Fallback to direct logging
            self._write_log_entry(entry)
    
    def log_signal(self, signal: TradingSignal, additional_data: Optional[Dict] = None):
        """
        Log trading signal with full context.
        
        Args:
            signal: Trading signal
            additional_data: Additional context data
        """
        signal_data = {
            'ticker': signal.ticker,
            'type': signal.signal_type,
            'confidence': signal.confidence,
            'price': signal.entry_price,
            'stop_loss': signal.stop_loss,
            'take_profit': signal.take_profit,
            'reason': signal.reason,
            'metadata': signal.metadata
        }
        
        if additional_data:
            signal_data.update(additional_data)
        
        # Format readable message
        message = (
            f"{signal.signal_type.upper()} {signal.ticker} @ "
            f"{format_currency(signal.entry_price)} "
            f"({signal.confidence:.0%} confidence) - {signal.reason}"
        )
        
        self.log('INFO', 'signals', message, signal_data)
        
        # Also log to main logger for visibility
        self.log('INFO', 'main', f"Signal: {message}")
    
    def log_trade_action(self, action: str, ticker: str, price: float, 
                        quantity: int, additional_data: Optional[Dict] = None):
        """
        Log trade actions (open/close positions).
        
        Args:
            action: Action type ('open', 'close', 'update')
            ticker: Stock symbol
            price: Trade price
            quantity: Number of shares
            additional_data: Additional trade data
        """
        trade_data = {
            'action': action,
            'ticker': ticker,
            'price': price,
            'quantity': quantity,
            'value': price * quantity
        }
        
        if additional_data:
            trade_data.update(additional_data)
        
        message = (
            f"{action.upper()} {ticker}: {quantity} shares @ "
            f"{format_currency(price)} = {format_currency(price * quantity)}"
        )
        
        self.log('INFO', 'audit', message, trade_data)
    
    def log_performance(self, metrics: Dict[str, Any]):
        """
        Log performance metrics.
        
        Args:
            metrics: Performance metrics dictionary
        """
        # Create readable summary
        summary_parts = []
        
        if 'total_signals' in metrics:
            summary_parts.append(f"Signals: {metrics['total_signals']}")
        
        if 'win_rate' in metrics:
            summary_parts.append(f"Win Rate: {metrics['win_rate']:.1%}")
        
        if 'total_pnl' in metrics:
            summary_parts.append(f"P&L: {format_currency(metrics['total_pnl'])}")
        
        if 'processing_time' in metrics:
            summary_parts.append(f"Processing: {metrics['processing_time']:.2f}s")
        
        message = "Performance: " + " | ".join(summary_parts)
        
        self.log('INFO', 'performance', message, metrics)
    
    def capture_snapshot(self, ticker: str, market_data: pd.DataFrame,
                        signal: Optional[TradingSignal] = None,
                        portfolio_state: Optional[Dict] = None):
        """
        Capture snapshot for replay functionality.
        
        Args:
            ticker: Stock symbol
            market_data: Complete market data with indicators
            signal: Generated signal (if any)
            portfolio_state: Current portfolio state
        """
        # Convert DataFrame to dict for serialization
        market_dict = {}
        if not market_data.empty:
            latest_row = market_data.iloc[-1]
            market_dict = {
                'timestamp': latest_row.name if hasattr(latest_row, 'name') else datetime.now(),
                'open': latest_row.get('open', 0),
                'high': latest_row.get('high', 0),
                'low': latest_row.get('low', 0),
                'close': latest_row.get('close', 0),
                'volume': latest_row.get('volume', 0),
                'rsi': latest_row.get('rsi', None),
                'psar': latest_row.get('psar', None),
                'engulfing_signal': latest_row.get('engulfing_signal', None),
                'volume_anomaly': latest_row.get('volume_anomaly', None)
            }
        
        snapshot = SignalSnapshot(
            timestamp=datetime.now(),
            ticker=ticker,
            market_data=market_dict,
            signal=signal,
            portfolio_state=portfolio_state or {}
        )
        
        self.snapshots.append(snapshot)
        
        # Keep only recent snapshots
        if len(self.snapshots) > self.max_snapshots:
            self.snapshots = self.snapshots[-self.max_snapshots:]
    
    def save_replay_data(self, filename: Optional[str] = None):
        """
        Save replay data to file.
        
        Args:
            filename: Output filename (auto-generated if None)
        """
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = self.log_dir / 'replay' / f'replay_{timestamp}.pkl.gz'
        
        replay_data = {
            'session_id': self.session_id,
            'timestamp': datetime.now(),
            'snapshots': [snapshot.to_dict() for snapshot in self.snapshots],
            'config_snapshot': self.config
        }
        
        try:
            with gzip.open(filename, 'wb') as f:
                pickle.dump(replay_data, f)
            
            self.log('INFO', 'main', f'Replay data saved: {filename}')
            
        except Exception as e:
            self.log('ERROR', 'main', f'Failed to save replay data: {str(e)}')
    
    def load_replay_data(self, filename: str) -> Dict[str, Any]:
        """
        Load replay data from file.
        
        Args:
            filename: Input filename
            
        Returns:
            Dict: Replay data
        """
        try:
            with gzip.open(filename, 'rb') as f:
                return pickle.load(f)
                
        except Exception as e:
            self.log('ERROR', 'main', f'Failed to load replay data: {str(e)}')
            return {}
    
    def replay_signals(self, replay_data: Dict[str, Any], 
                      start_time: Optional[datetime] = None,
                      end_time: Optional[datetime] = None) -> List[Dict]:
        """
        Replay signals from saved data.
        
        Args:
            replay_data: Loaded replay data
            start_time: Start time for replay (optional)
            end_time: End time for replay (optional)
            
        Returns:
            List[Dict]: Replayed signal events
        """
        snapshots = replay_data.get('snapshots', [])
        replayed_events = []
        
        for snapshot_dict in snapshots:
            # Parse timestamp
            event_time = datetime.fromisoformat(snapshot_dict['timestamp'])
            
            # Apply time filters
            if start_time and event_time < start_time:
                continue
            if end_time and event_time > end_time:
                continue
            
            # Extract signal if present
            signal_data = snapshot_dict.get('signal')
            if signal_data:
                event = {
                    'timestamp': event_time,
                    'ticker': snapshot_dict['ticker'],
                    'signal_type': signal_data['signal_type'],
                    'confidence': signal_data['confidence'],
                    'entry_price': signal_data['entry_price'],
                    'reason': signal_data['reason'],
                    'market_data': snapshot_dict['market_data'],
                    'portfolio_state': snapshot_dict['portfolio_state']
                }
                
                replayed_events.append(event)
        
        self.log('INFO', 'main', f'Replayed {len(replayed_events)} signal events')
        return replayed_events
    
    def get_log_summary(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get log summary for recent period.
        
        Args:
            hours: Hours to look back
            
        Returns:
            Dict: Log summary statistics
        """
        # This would typically query log files or database
        # For now, return basic info
        return {
            'session_id': self.session_id,
            'log_dir': str(self.log_dir),
            'snapshots_captured': len(self.snapshots),
            'last_snapshot': self.snapshots[-1].timestamp if self.snapshots else None,
            'log_files': {
                'main': str(self.log_dir / f'main_{self.session_id}.log'),
                'signals': str(self.log_dir / 'signals' / f'signals_{self.session_id}.log'),
                'audit': str(self.log_dir / 'audit' / f'audit_{self.session_id}.log'),
                'performance': str(self.log_dir / f'performance_{self.session_id}.log')
            }
        }
    
    def cleanup_old_logs(self, days: int = 30):
        """
        Clean up log files older than specified days.
        
        Args:
            days: Keep logs for this many days
        """
        cutoff_time = datetime.now() - timedelta(days=days)
        cleaned_count = 0
        
        try:
            for log_file in self.log_dir.rglob('*.log*'):
                if log_file.stat().st_mtime < cutoff_time.timestamp():
                    log_file.unlink()
                    cleaned_count += 1
            
            # Clean old replay files
            for replay_file in (self.log_dir / 'replay').glob('*.pkl.gz'):
                if replay_file.stat().st_mtime < cutoff_time.timestamp():
                    replay_file.unlink()
                    cleaned_count += 1
            
            self.log('INFO', 'main', f'Cleaned up {cleaned_count} old log files')
            
        except Exception as e:
            self.log('ERROR', 'main', f'Log cleanup failed: {str(e)}')


# Convenience functions for global logger
_global_logger: Optional[StructuredLogger] = None

def initialize_global_logger(config: Dict[str, Any], session_id: str = None) -> StructuredLogger:
    """Initialize global logger instance."""
    global _global_logger
    _global_logger = StructuredLogger(config, session_id)
    _global_logger.start_async_logging()
    return _global_logger

def get_logger() -> Optional[StructuredLogger]:
    """Get global logger instance."""
    return _global_logger

def log_signal(signal: TradingSignal, **kwargs):
    """Convenience function to log signal."""
    if _global_logger:
        _global_logger.log_signal(signal, **kwargs)

def log_trade(action: str, ticker: str, price: float, quantity: int, **kwargs):
    """Convenience function to log trade."""
    if _global_logger:
        _global_logger.log_trade_action(action, ticker, price, quantity, **kwargs)

def log_performance(metrics: Dict[str, Any]):
    """Convenience function to log performance."""
    if _global_logger:
        _global_logger.log_performance(metrics)
