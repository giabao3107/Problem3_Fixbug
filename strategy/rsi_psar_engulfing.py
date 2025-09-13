"""
RSI-PSAR-Engulfing Trading Strategy Implementation
Combines RSI, Parabolic SAR, and Engulfing patterns for signal generation.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import logging

from utils.indicators import TechnicalIndicators
from utils.helpers import DataCache
from strategy.risk_management import RiskManager


@dataclass
class TradingSignal:
    """Trading signal data structure."""
    ticker: str
    timestamp: datetime
    signal_type: str  # 'buy', 'sell', 'risk_warning'
    confidence: float  # 0.0 to 1.0
    entry_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    reason: str = ""
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class StrategyState:
    """Current state of the strategy for a ticker."""
    ticker: str
    last_update: datetime
    current_price: float
    position_status: str  # 'none', 'long', 'short'
    entry_price: Optional[float] = None
    entry_date: Optional[datetime] = None
    unrealized_pnl: float = 0.0
    max_price_since_entry: float = 0.0
    trailing_stop_price: Optional[float] = None
    last_signal_type: Optional[str] = None
    last_signal_time: Optional[datetime] = None


class RSIPSAREngulfingStrategy:
    """
    Main trading strategy combining RSI, PSAR, and Engulfing patterns.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize strategy with configuration parameters.
        
        Args:
            config: Strategy configuration dictionary
        """
        self.config = config
        self.strategy_config = config.get('strategy', {})
        
        # Strategy parameters
        self.rsi_config = self.strategy_config.get('rsi', {})
        self.psar_config = self.strategy_config.get('psar', {})
        self.engulfing_config = self.strategy_config.get('engulfing', {})
        self.volume_config = self.strategy_config.get('volume', {})
        
        # Risk management
        self.risk_manager = RiskManager(config.get('risk_management', {}))
        
        # State tracking
        self.ticker_states: Dict[str, StrategyState] = {}
        self.signal_history: List[TradingSignal] = []
        
        # Caching for performance
        self.data_cache = DataCache(default_ttl=300)  # 5 minutes
        
        self.logger = logging.getLogger(__name__)
    
    def analyze_ticker(self, ticker: str, df: pd.DataFrame) -> List[TradingSignal]:
        """
        Analyze a ticker and generate trading signals.
        
        Args:
            ticker: Stock symbol
            df: OHLCV DataFrame with sufficient history
            
        Returns:
            List[TradingSignal]: Generated signals
        """
        if df.empty or len(df) < 50:  # Need sufficient history
            self.logger.warning(f"Insufficient data for {ticker}: {len(df)} rows")
            return []
        
        try:
            # Calculate all indicators
            df_with_indicators = self._calculate_indicators(df)
            
            # Generate signals
            signals = self._generate_signals(ticker, df_with_indicators)
            
            # Update ticker state
            self._update_ticker_state(ticker, df_with_indicators)
            
            # Apply risk management
            signals = self._apply_risk_management(ticker, signals)
            
            return signals
            
        except Exception as e:
            self.logger.error(f"Error analyzing {ticker}: {str(e)}")
            return []
    
    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all technical indicators."""
        return TechnicalIndicators.calculate_all_indicators(
            df,
            rsi_period=self.rsi_config.get('period', 14),
            psar_af_init=self.psar_config.get('af_init', 0.02),
            psar_af_step=self.psar_config.get('af_step', 0.02),
            psar_af_max=self.psar_config.get('af_max', 0.20),
            engulfing_min_body_ratio=self.engulfing_config.get('min_body_ratio', 0.5),
            volume_avg_period=self.volume_config.get('avg_period', 20),
            volume_anomaly_threshold=self.volume_config.get('anomaly_threshold', 1.0)
        )
    
    def _generate_signals(self, ticker: str, df: pd.DataFrame) -> List[TradingSignal]:
        """Generate trading signals based on strategy rules."""
        signals = []
        current_row = df.iloc[-1]
        current_time = datetime.now()
        
        # Get current position state
        current_state = self.ticker_states.get(ticker)
        
        # Check for buy signals
        buy_signal = self._check_buy_conditions(current_row)
        if buy_signal['signal']:
            signal = TradingSignal(
                ticker=ticker,
                timestamp=current_time,
                signal_type='buy',
                confidence=buy_signal['confidence'],
                entry_price=current_row['close'],
                stop_loss=self._calculate_stop_loss(current_row['close'], 'long'),
                take_profit=self._calculate_take_profit(current_row['close'], 'long'),
                reason=buy_signal['reason'],
                metadata={
                    'rsi': current_row.get('rsi', 0),
                    'psar': current_row.get('psar', 0),
                    'price_vs_psar': current_row.get('price_vs_psar', 0),
                    'engulfing_signal': current_row.get('engulfing_signal', 0),
                    'engulfing_in_3_candles': current_row.get('engulfing_in_3_candles', 0),
                    'volume_anomaly': current_row.get('volume_anomaly', 0)
                }
            )
            signals.append(signal)
        
        # Check for sell signals (only if in position)
        if current_state and current_state.position_status == 'long':
            sell_signal = self._check_sell_conditions(ticker, current_row)
            if sell_signal['signal']:
                signal = TradingSignal(
                    ticker=ticker,
                    timestamp=current_time,
                    signal_type='sell',
                    confidence=sell_signal['confidence'],
                    entry_price=current_row['close'],
                    reason=sell_signal['reason'],
                    metadata={
                        'entry_price': current_state.entry_price,
                        'pnl_percent': sell_signal.get('pnl_percent', 0),
                        'days_held': (current_time - current_state.entry_date).days if current_state.entry_date else 0
                    }
                )
                signals.append(signal)
        
        # Check for risk warnings
        risk_signal = self._check_risk_conditions(ticker, current_row)
        if risk_signal['signal']:
            signal = TradingSignal(
                ticker=ticker,
                timestamp=current_time,
                signal_type='risk_warning',
                confidence=risk_signal['confidence'],
                entry_price=current_row['close'],
                reason=risk_signal['reason'],
                metadata=risk_signal.get('metadata', {})
            )
            signals.append(signal)
        
        return signals
    
    def _check_buy_conditions(self, row: pd.Series) -> Dict[str, Any]:
        """
        Check if buy conditions are met.
        
        Main conditions:
        - Close > PSAR (uptrend)
        - RSI > 50 (momentum)
        
        Optional conditions:
        - Volume > Average Volume (confirmation)
        - Bullish Engulfing in last 3 candles
        """
        conditions = []
        reasons = []
        
        # Core conditions
        close = row.get('close', 0)
        psar = row.get('psar', 0)
        rsi = row.get('rsi', 50)
        
        price_above_psar = close > psar if psar > 0 else False
        rsi_bullish = rsi > self.rsi_config.get('neutral', 50)
        
        if price_above_psar:
            conditions.append(True)
            reasons.append("Price > PSAR")
        else:
            conditions.append(False)
            
        if rsi_bullish:
            conditions.append(True)
            reasons.append(f"RSI > {self.rsi_config.get('neutral', 50)}")
        else:
            conditions.append(False)
        
        # Core conditions must be met
        core_met = all(conditions)
        
        # Optional conditions (boost confidence)
        volume_anomaly = row.get('volume_anomaly', 0) == 1
        bullish_engulfing = row.get('engulfing_in_3_candles', 0) == 1
        
        confidence = 0.6 if core_met else 0.0  # Base confidence
        
        if volume_anomaly:
            confidence += 0.2
            reasons.append("Volume Anomaly")
            
        if bullish_engulfing:
            confidence += 0.2
            reasons.append("Bullish Engulfing ≤3 candles")
        
        # Additional liquidity and market conditions
        if self._check_liquidity_filters(row):
            confidence = min(1.0, confidence + 0.1)
            reasons.append("Liquidity OK")
        else:
            confidence *= 0.7  # Reduce confidence for poor liquidity
        
        return {
            'signal': core_met and confidence >= 0.6,
            'confidence': confidence,
            'reason': ', '.join(reasons) if reasons else 'No conditions met'
        }
    
    def _check_sell_conditions(self, ticker: str, row: pd.Series) -> Dict[str, Any]:
        """
        Check if sell conditions are met.
        
        Exit conditions:
        - RSI < 50 (momentum loss)
        - Bearish Engulfing pattern
        - Take Profit hit (+15%)
        - Stop Loss hit (-8%)
        - Trailing Stop (3% from peak after +9%)
        """
        current_state = self.ticker_states.get(ticker)
        if not current_state or current_state.position_status != 'long':
            return {'signal': False, 'confidence': 0.0, 'reason': 'No position'}
        
        current_price = row.get('close', 0)
        entry_price = current_state.entry_price
        
        if not entry_price or entry_price <= 0:
            return {'signal': False, 'confidence': 0.0, 'reason': 'Invalid entry price'}
        
        # Calculate PnL
        pnl_percent = (current_price - entry_price) / entry_price
        
        reasons = []
        confidence = 0.0
        
        # Check take profit
        tp_threshold = self.risk_manager.config.get('take_profit', 0.15)
        if pnl_percent >= tp_threshold:
            return {
                'signal': True,
                'confidence': 1.0,
                'reason': f'Take Profit hit (+{pnl_percent*100:.1f}%)',
                'pnl_percent': pnl_percent
            }
        
        # Check stop loss
        sl_threshold = -abs(self.risk_manager.config.get('stop_loss', 0.08))
        if pnl_percent <= sl_threshold:
            return {
                'signal': True,
                'confidence': 1.0,
                'reason': f'Stop Loss hit ({pnl_percent*100:.1f}%)',
                'pnl_percent': pnl_percent
            }
        
        # Check trailing stop
        trailing_tp = self.risk_manager.config.get('trailing_take_profit', 0.09)
        trailing_sl = self.risk_manager.config.get('trailing_stop', 0.03)
        
        # Update max price since entry
        if current_price > current_state.max_price_since_entry:
            current_state.max_price_since_entry = current_price
        
        # Check if we should activate trailing stop
        max_pnl_percent = (current_state.max_price_since_entry - entry_price) / entry_price
        
        if max_pnl_percent >= trailing_tp:  # Activate trailing stop after +9%
            # Calculate trailing stop price
            trailing_stop_price = current_state.max_price_since_entry * (1 - trailing_sl)
            current_state.trailing_stop_price = trailing_stop_price
            
            if current_price <= trailing_stop_price:
                return {
                    'signal': True,
                    'confidence': 1.0,
                    'reason': f'Trailing Stop hit (peak: +{max_pnl_percent*100:.1f}%, current: {pnl_percent*100:.1f}%)',
                    'pnl_percent': pnl_percent
                }
        
        # Technical exit conditions
        rsi = row.get('rsi', 50)
        engulfing_signal = row.get('engulfing_signal', 0)
        
        # RSI below neutral
        if rsi < self.rsi_config.get('neutral', 50):
            confidence += 0.4
            reasons.append("RSI < 50")
        
        # Bearish engulfing
        if engulfing_signal < 0:  # Bearish engulfing
            confidence += 0.6
            reasons.append("Bearish Engulfing")
        
        return {
            'signal': confidence >= 0.7,
            'confidence': confidence,
            'reason': ', '.join(reasons) if reasons else 'No exit conditions',
            'pnl_percent': pnl_percent
        }
    
    def _check_risk_conditions(self, ticker: str, row: pd.Series) -> Dict[str, Any]:
        """
        Check for risk warning conditions.
        
        Risk factors:
        - High volatility spike
        - Low liquidity
        - Large spread
        - Unusual volume patterns
        """
        reasons = []
        confidence = 0.0
        metadata = {}
        
        # Volume spike detection
        volume = row.get('volume', 0)
        avg_volume = row.get('avg_volume_20', 0)
        
        if volume > 0 and avg_volume > 0:
            volume_ratio = volume / avg_volume
            if volume_ratio > 3.0:  # 3x average volume
                confidence += 0.3
                reasons.append(f"Volume spike ({volume_ratio:.1f}x avg)")
                metadata['volume_ratio'] = volume_ratio
        
        # Price volatility (can be enhanced with actual volatility calculation)
        high = row.get('high', 0)
        low = row.get('low', 0)
        close = row.get('close', 0)
        
        if close > 0:
            daily_range = (high - low) / close
            if daily_range > 0.05:  # 5% daily range
                confidence += 0.2
                reasons.append(f"High volatility ({daily_range*100:.1f}%)")
                metadata['daily_range_percent'] = daily_range * 100
        
        # RSI extreme levels
        rsi = row.get('rsi', 50)
        if rsi > self.rsi_config.get('overbought', 70):
            confidence += 0.3
            reasons.append(f"RSI overbought ({rsi:.1f})")
        elif rsi < self.rsi_config.get('oversold', 30):
            confidence += 0.2
            reasons.append(f"RSI oversold ({rsi:.1f})")
        
        return {
            'signal': confidence >= 0.4,
            'confidence': confidence,
            'reason': ', '.join(reasons) if reasons else 'No risk factors',
            'metadata': metadata
        }
    
    def _check_liquidity_filters(self, row: pd.Series) -> bool:
        """Check basic liquidity and quality filters."""
        volume = row.get('volume', 0)
        close = row.get('close', 0)
        
        # Minimum volume threshold
        if volume < 10000:  # Minimum 10k shares
            return False
        
        # Reasonable price range
        if close < 1000 or close > 1000000:  # 1k - 1M VND
            return False
        
        return True
    
    def _calculate_stop_loss(self, entry_price: float, direction: str) -> float:
        """Calculate stop loss price."""
        sl_percent = self.risk_manager.config.get('stop_loss', 0.08)
        
        if direction == 'long':
            return entry_price * (1 - sl_percent)
        else:  # short
            return entry_price * (1 + sl_percent)
    
    def _calculate_take_profit(self, entry_price: float, direction: str) -> float:
        """Calculate take profit price."""
        tp_percent = self.risk_manager.config.get('take_profit', 0.15)
        
        if direction == 'long':
            return entry_price * (1 + tp_percent)
        else:  # short
            return entry_price * (1 - tp_percent)
    
    def _update_ticker_state(self, ticker: str, df: pd.DataFrame):
        """Update internal state for ticker."""
        current_row = df.iloc[-1]
        current_time = datetime.now()
        
        if ticker not in self.ticker_states:
            self.ticker_states[ticker] = StrategyState(
                ticker=ticker,
                last_update=current_time,
                current_price=current_row['close'],
                position_status='none'
            )
        else:
            state = self.ticker_states[ticker]
            state.last_update = current_time
            state.current_price = current_row['close']
            
            # Update unrealized PnL if in position
            if state.position_status == 'long' and state.entry_price:
                state.unrealized_pnl = (state.current_price - state.entry_price) / state.entry_price
    
    def _apply_risk_management(self, ticker: str, signals: List[TradingSignal]) -> List[TradingSignal]:
        """Apply risk management rules to filter signals."""
        return self.risk_manager.filter_signals(ticker, signals, self.ticker_states)
    
    def update_position_status(self, ticker: str, new_status: str, 
                             entry_price: Optional[float] = None,
                             entry_time: Optional[datetime] = None):
        """
        Update position status for a ticker.
        
        Args:
            ticker: Stock symbol
            new_status: New position status ('none', 'long', 'short')
            entry_price: Entry price if opening position
            entry_time: Entry time if opening position
        """
        if ticker not in self.ticker_states:
            self.ticker_states[ticker] = StrategyState(
                ticker=ticker,
                last_update=datetime.now(),
                current_price=entry_price or 0,
                position_status=new_status
            )
        
        state = self.ticker_states[ticker]
        state.position_status = new_status
        
        if new_status in ['long', 'short']:
            state.entry_price = entry_price
            state.entry_date = entry_time or datetime.now()
            state.max_price_since_entry = entry_price or 0
            state.trailing_stop_price = None
        else:  # 'none'
            state.entry_price = None
            state.entry_date = None
            state.unrealized_pnl = 0.0
            state.max_price_since_entry = 0.0
            state.trailing_stop_price = None
    
    def get_ticker_state(self, ticker: str) -> Optional[StrategyState]:
        """Get current state for ticker."""
        return self.ticker_states.get(ticker)
    
    def get_active_positions(self) -> Dict[str, StrategyState]:
        """Get all tickers with active positions."""
        return {
            ticker: state for ticker, state in self.ticker_states.items()
            if state.position_status != 'none'
        }
    
    def get_signal_history(self, limit: int = 100) -> List[TradingSignal]:
        """Get recent signal history."""
        return self.signal_history[-limit:] if limit > 0 else self.signal_history
    
    def add_signal_to_history(self, signal: TradingSignal):
        """Add signal to history."""
        self.signal_history.append(signal)
        
        # Keep history manageable
        if len(self.signal_history) > 1000:
            self.signal_history = self.signal_history[-500:]
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Calculate basic performance statistics."""
        if not self.signal_history:
            return {}
        
        signals_df = pd.DataFrame([
            {
                'ticker': s.ticker,
                'timestamp': s.timestamp,
                'type': s.signal_type,
                'confidence': s.confidence,
                'price': s.entry_price
            }
            for s in self.signal_history
        ])
        
        stats = {
            'total_signals': len(self.signal_history),
            'buy_signals': len(signals_df[signals_df['type'] == 'buy']),
            'sell_signals': len(signals_df[signals_df['type'] == 'sell']),
            'risk_warnings': len(signals_df[signals_df['type'] == 'risk_warning']),
            'avg_confidence': signals_df['confidence'].mean(),
            'active_positions': len(self.get_active_positions()),
            'unique_tickers': signals_df['ticker'].nunique()
        }
        
        return stats
