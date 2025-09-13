"""
Real-time Market Monitor
Main application that coordinates data fetching, signal generation, and alerts.
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import pandas as pd
import schedule
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from pathlib import Path

# Import project modules
from utils.helpers import (
    load_config, load_symbols, setup_logging, is_trading_hours,
    get_env_variable, save_to_csv, DataCache, CircuitBreaker
)
from utils.fiinquant_adapter import FiinQuantAdapter
from strategy.rsi_psar_engulfing import RSIPSAREngulfingStrategy, TradingSignal
from jobs.telegram_bot import TradingTelegramBot
from database.data_manager import DatabaseManager


class RealtimeMonitor:
    """
    Main real-time monitoring application.
    Orchestrates data fetching, analysis, and alert generation.
    """
    
    def __init__(self, config_path: str = "config/config.yaml"):
        """
        Initialize real-time monitor.
        
        Args:
            config_path: Path to configuration file
        """
        # Load configuration
        self.config = load_config(config_path)
        
        # Setup logging
        self.logger = setup_logging(self.config)
        self.logger.info("Initializing Real-time Monitor with FiinQuant data")
        
        # Initialize components
        self._initialize_components()
        
        # Runtime state
        self.is_running = False
        self.last_update_time = None
        self.update_count = 0
        self.error_count = 0
        
        # Performance tracking
        self.processing_times = []
        self.signal_counts = {'buy': 0, 'sell': 0, 'risk_warning': 0}
        
        # Circuit breaker for error handling
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=300  # 5 minutes
        )
        
        # Setup graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _initialize_components(self):
        """Initialize all system components."""
        try:
            # Data adapter - FiinQuant only
            username = get_env_variable('FIINQUANT_USERNAME', required=True)
            password = get_env_variable('FIINQUANT_PASSWORD', required=True)
            
            self.logger.info("Initializing FiinQuant data adapter")
            data_config = self.config.get('data_source', {})
            self.data_adapter = FiinQuantAdapter(
                username=username,
                password=password,
                retry_attempts=data_config.get('retry_attempts', 3),
                retry_delay=data_config.get('retry_delay', 5)
            )
            
            # Trading strategy
            self.strategy = RSIPSAREngulfingStrategy(self.config)
            
            # Telegram bot
            self.telegram_bot = TradingTelegramBot(self.config)
            
            # Database manager
            self.db_manager = DatabaseManager(self.config)
            
            # Symbol universe
            symbols = load_symbols()
            
            # Use all symbols from all exchanges if available
            if symbols.get('universe', {}).get('all_exchanges_list'):
                self.universe = symbols.get('universe', {}).get('all_exchanges_list', [])
                self.logger.info(f"Monitoring ALL symbols from HOSE, HNX, UPCOM: {len(self.universe)} symbols")
            else:
                # Fallback to VN30 if all symbols are not available
                self.universe = symbols.get('universe', {}).get('vn30', [])
                self.logger.info(f"Monitoring VN30 symbols: {len(self.universe)} symbols")
            
            # Cache for data
            self.data_cache = DataCache(default_ttl=300)  # 5 minutes
            
            # Configuration
            self.refresh_interval = int(get_env_variable('REFRESH_INTERVAL_SECONDS', 60))
            self.timeframe = get_env_variable('TIMEFRAME', '15m')
            
            self.logger.info("All components initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize components: {str(e)}")
            raise
    
    async def start(self):
        """Start the real-time monitoring system."""
        self.logger.info("Starting Real-time Monitor")
        
        try:
            # Initialize database
            await self.db_manager.initialize()
            
            # Initialize data adapter
            if not self.data_adapter.login():
                raise Exception("Failed to login to data source")
            
            # Initialize Telegram bot
            await self.telegram_bot.initialize()
            await self.telegram_bot.start_bot()
            
            # Send startup notification
            await self.telegram_bot.send_system_alert(
                f"🚀 Real-time Monitor Started\n\n"
                f"Monitoring: {len(self.universe)} symbols\n"
                f"Timeframe: {self.timeframe}\n"
                f"Refresh: {self.refresh_interval}s",
                "info"
            )
            
            # Set running flag
            self.is_running = True
            
            # Schedule periodic tasks
            self._setup_schedules()
            
            # Start main monitoring loop
            await self._main_loop()
            
        except Exception as e:
            self.logger.error(f"Failed to start monitor: {str(e)}")
            await self._shutdown()
            raise
    
    def _setup_schedules(self):
        """Setup scheduled tasks."""
        # Main data update
        schedule.every(self.refresh_interval).seconds.do(self._schedule_update)
        
        # Health check every 5 minutes
        schedule.every(5).minutes.do(self._schedule_health_check)
        
        # Daily cleanup at midnight
        schedule.every().day.at("00:01").do(self._schedule_daily_cleanup)
        
        # Performance report every hour
        schedule.every().hour.do(self._schedule_performance_report)
        
        self.logger.info("Scheduled tasks configured")
    
    def _schedule_update(self):
        """Scheduled data update wrapper."""
        try:
            if is_trading_hours(self.config):
                asyncio.create_task(self._update_cycle())
        except Exception as e:
            self.logger.error(f"Scheduled update error: {str(e)}")
    
    def _schedule_health_check(self):
        """Scheduled health check."""
        try:
            self._log_health_status()
        except Exception as e:
            self.logger.error(f"Health check error: {str(e)}")
    
    def _schedule_daily_cleanup(self):
        """Daily cleanup tasks."""
        try:
            asyncio.create_task(self._daily_cleanup())
        except Exception as e:
            self.logger.error(f"Daily cleanup error: {str(e)}")
    
    def _schedule_performance_report(self):
        """Hourly performance report."""
        try:
            asyncio.create_task(self._send_performance_report())
        except Exception as e:
            self.logger.error(f"Performance report error: {str(e)}")
    
    async def _main_loop(self):
        """Main monitoring loop."""
        self.logger.info("Starting main monitoring loop")
        
        while self.is_running:
            try:
                # Check if in trading hours
                if not is_trading_hours(self.config):
                    await asyncio.sleep(300)  # Check every 5 minutes outside hours
                    continue
                
                # Run scheduled tasks
                schedule.run_pending()
                
                # Short sleep to prevent high CPU usage
                await asyncio.sleep(1)
                
            except Exception as e:
                self.logger.error(f"Main loop error: {str(e)}")
                self.error_count += 1
                
                # If too many errors, activate circuit breaker
                if self.error_count > 10:
                    self.logger.critical("Too many errors, activating circuit breaker")
                    await asyncio.sleep(60)  # Cool down period
                    self.error_count = 0
    
    async def _update_cycle(self):
        """Single update cycle - fetch data and analyze signals."""
        start_time = time.time()
        
        try:
            # Use circuit breaker
            await self.circuit_breaker.call(self._perform_update_cycle)
            
            # Record successful cycle
            processing_time = time.time() - start_time
            self.processing_times.append(processing_time)
            
            # Keep last 100 processing times
            if len(self.processing_times) > 100:
                self.processing_times = self.processing_times[-100:]
            
            self.update_count += 1
            self.last_update_time = datetime.now()
            
            self.logger.debug(f"Update cycle completed in {processing_time:.2f}s")
            
        except Exception as e:
            self.error_count += 1
            self.logger.error(f"Update cycle failed: {str(e)}")
            
            # Send error alert if too many failures
            if self.error_count > 5:
                await self.telegram_bot.send_system_alert(
                    f"⚠️ Multiple update failures detected\n"
                    f"Error count: {self.error_count}\n"
                    f"Last error: {str(e)[:100]}",
                    "warning"
                )
    
    async def _perform_update_cycle(self):
        """Perform the actual update cycle."""
        # Batch process tickers for efficiency
        batch_size = 10
        ticker_batches = [
            self.universe[i:i + batch_size]
            for i in range(0, len(self.universe), batch_size)
        ]
        
        all_signals = []
        
        # Process each batch
        for batch in ticker_batches:
            batch_signals = await self._process_ticker_batch(batch)
            all_signals.extend(batch_signals)
        
        # Process all signals
        if all_signals:
            await self._process_signals(all_signals)
        
        self.logger.debug(f"Processed {len(self.universe)} tickers, generated {len(all_signals)} signals")
    
    async def _process_ticker_batch(self, tickers: List[str]) -> List[TradingSignal]:
        """Process a batch of tickers in parallel."""
        signals = []
        
        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=5) as executor:
            # Submit tasks
            future_to_ticker = {
                executor.submit(self._analyze_ticker, ticker): ticker
                for ticker in tickers
            }
            
            # Collect results
            for future in as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    ticker_signals = future.result()
                    signals.extend(ticker_signals)
                except Exception as e:
                    self.logger.error(f"Error processing {ticker}: {str(e)}")
        
        return signals
    
    def _analyze_ticker(self, ticker: str) -> List[TradingSignal]:
        """Analyze single ticker and return signals."""
        try:
            # Check cache first
            cache_key = f"data_{ticker}_{self.timeframe}"
            cached_data = self.data_cache.get(cache_key)
            
            if cached_data is None:
                # Fetch fresh data
                df = self.data_adapter.fetch_historical_data(
                    tickers=[ticker],
                    timeframe=self.timeframe,
                    period=100  # Sufficient for indicators
                )
                
                if df.empty:
                    self.logger.warning(f"No data for {ticker}")
                    return []
                
                # Cache the data
                self.data_cache.set(cache_key, df, ttl=60)  # 1 minute cache
            else:
                df = cached_data
            
            # Analyze with strategy
            signals = self.strategy.analyze_ticker(ticker, df)
            
            return signals
            
        except Exception as e:
            self.logger.error(f"Failed to analyze {ticker}: {str(e)}")
            return []
    
    async def _process_signals(self, signals: List[TradingSignal]):
        """Process and distribute generated signals."""
        for signal in signals:
            try:
                # Log signal
                self.logger.info(
                    f"Signal: {signal.signal_type.upper()} {signal.ticker} "
                    f"@ {signal.entry_price:.0f} (confidence: {signal.confidence:.0%})"
                )
                
                # Update signal counts
                self.signal_counts[signal.signal_type] = \
                    self.signal_counts.get(signal.signal_type, 0) + 1
                
                # Add to strategy history
                self.strategy.add_signal_to_history(signal)
                
                # Send to Telegram
                await self.telegram_bot.send_trading_signal(signal)
                
                # Save to database
                await self.db_manager.save_signal(signal)
                
                # Save to CSV log
                self._save_signal_to_csv(signal)
                
            except Exception as e:
                self.logger.error(f"Failed to process signal: {str(e)}")
    
    def _save_signal_to_csv(self, signal: TradingSignal):
        """Save signal to CSV log file."""
        try:
            log_dir = Path("log")
            log_dir.mkdir(exist_ok=True)
            
            log_file = log_dir / "signals_log.csv"
            
            # Create DataFrame for signal
            signal_df = pd.DataFrame([{
                'timestamp': signal.timestamp,
                'timeframe': self.timeframe,
                'ticker': signal.ticker,
                'price': signal.entry_price,
                'signal_type': signal.signal_type,
                'confidence': signal.confidence,
                'reason': signal.reason,
                'stop_loss': signal.stop_loss,
                'take_profit': signal.take_profit,
                'metadata': str(signal.metadata) if signal.metadata else ''
            }])
            
            save_to_csv(signal_df, str(log_file), append=True)
            
        except Exception as e:
            self.logger.error(f"Failed to save signal to CSV: {str(e)}")
    
    def _log_health_status(self):
        """Log system health status."""
        try:
            # Data adapter health
            adapter_health = self.data_adapter.health_check()
            
            # Bot health
            bot_health = self.telegram_bot.get_bot_status()
            
            # Strategy health
            strategy_stats = self.strategy.get_performance_stats()
            
            # System metrics
            avg_processing_time = (
                sum(self.processing_times) / len(self.processing_times)
                if self.processing_times else 0
            )
            
            health_report = {
                'timestamp': datetime.now().isoformat(),
                'update_count': self.update_count,
                'error_count': self.error_count,
                'avg_processing_time': avg_processing_time,
                'signal_counts': self.signal_counts,
                'adapter_health': adapter_health,
                'bot_health': bot_health,
                'strategy_stats': strategy_stats
            }
            
            self.logger.info(f"Health Status: {health_report}")
            
        except Exception as e:
            self.logger.error(f"Health check failed: {str(e)}")
    
    async def _send_performance_report(self):
        """Send hourly performance report via Telegram."""
        try:
            # Calculate metrics
            total_signals = sum(self.signal_counts.values())
            avg_processing_time = (
                sum(self.processing_times) / len(self.processing_times)
                if self.processing_times else 0
            )
            
            report = (
                f"📊 *Hourly Performance Report*\n\n"
                f"⏰ *Period:* {datetime.now().strftime('%H:00 - %H:59')}\n"
                f"🔄 *Updates:* {self.update_count}\n"
                f"⚡ *Avg Processing:* {avg_processing_time:.2f}s\n"
                f"🚨 *Total Signals:* {total_signals}\n\n"
                f"📈 *Signal Breakdown:*\n"
                f"🟢 Buy: {self.signal_counts.get('buy', 0)}\n"
                f"🔴 Sell: {self.signal_counts.get('sell', 0)}\n"
                f"🟠 Risk: {self.signal_counts.get('risk_warning', 0)}\n\n"
                f"❌ *Errors:* {self.error_count}"
            )
            
            await self.telegram_bot.send_message(report)
            
            # Reset hourly counters
            self.signal_counts = {'buy': 0, 'sell': 0, 'risk_warning': 0}
            self.error_count = 0
            
        except Exception as e:
            self.logger.error(f"Failed to send performance report: {str(e)}")
    
    async def _daily_cleanup(self):
        """Perform daily cleanup tasks."""
        try:
            self.logger.info("Performing daily cleanup")
            
            # Clean up old cache entries
            self.data_cache.cleanup()
            
            # Clean up old logs (keep last 30 days)
            await self.db_manager.cleanup_old_data(days=30)
            
            # Send daily summary
            await self._send_daily_summary()
            
        except Exception as e:
            self.logger.error(f"Daily cleanup failed: {str(e)}")
    
    async def _send_daily_summary(self):
        """Send daily trading summary."""
        try:
            # Get strategy performance
            strategy_stats = self.strategy.get_performance_stats()
            
            summary = (
                f"📈 *Daily Summary* - {datetime.now().strftime('%Y-%m-%d')}\n\n"
                f"🎯 *Strategy Performance:*\n"
                f"📊 Total Signals: {strategy_stats.get('total_signals', 0)}\n"
                f"🟢 Buy Signals: {strategy_stats.get('buy_signals', 0)}\n"
                f"🔴 Sell Signals: {strategy_stats.get('sell_signals', 0)}\n"
                f"🟠 Risk Warnings: {strategy_stats.get('risk_warnings', 0)}\n"
                f"💼 Active Positions: {strategy_stats.get('active_positions', 0)}\n\n"
                f"📋 *System Health:*\n"
                f"✅ Updates: {self.update_count}\n"
                f"⚠️ Errors: {self.error_count}\n"
                f"📡 Data Source: {'Mock' if self.use_mock_data else 'FiinQuant'}"
            )
            
            await self.telegram_bot.send_message(summary)
            
        except Exception as e:
            self.logger.error(f"Failed to send daily summary: {str(e)}")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.is_running = False
        
        # Run shutdown in event loop
        loop = asyncio.get_event_loop()
        loop.create_task(self._shutdown())
    
    async def _shutdown(self):
        """Graceful shutdown of all components."""
        self.logger.info("Shutting down Real-time Monitor")
        
        try:
            self.is_running = False
            
            # Send shutdown notification
            await self.telegram_bot.send_system_alert(
                "🛑 Real-time Monitor Shutting Down\n\n"
                "System is stopping gracefully.",
                "info"
            )
            
            # Stop components
            if hasattr(self, 'telegram_bot'):
                await self.telegram_bot.stop_bot()
            
            if hasattr(self, 'data_adapter'):
                self.data_adapter.stop_realtime_stream()
            
            if hasattr(self, 'db_manager'):
                await self.db_manager.close()
            
            self.logger.info("Shutdown completed")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {str(e)}")
        
        # Exit
        sys.exit(0)


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Real-time Trading Monitor')
    parser.add_argument('--config', default='config/config.yaml', help='Config file path')
    parser.add_argument('--mock', action='store_true', help='Use mock data')
    parser.add_argument('--log-level', default='INFO', help='Log level')
    
    args = parser.parse_args()
    
    # Setup basic logging for startup
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create and start monitor
    monitor = RealtimeMonitor(
        config_path=args.config,
        use_mock_data=args.mock
    )
    
    try:
        await monitor.start()
    except KeyboardInterrupt:
        logging.info("Received keyboard interrupt")
    except Exception as e:
        logging.error(f"Monitor failed: {str(e)}")
        logging.error(traceback.format_exc())
    finally:
        await monitor._shutdown()


if __name__ == "__main__":
    asyncio.run(main())
