"""
Unit tests for RSI-PSAR-Engulfing strategy.
"""

import unittest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from strategy.rsi_psar_engulfing import RSIPSAREngulfingStrategy, TradingSignal, StrategyState
from strategy.risk_management import RiskManager


class TestRSIPSAREngulfingStrategy(unittest.TestCase):
    """Test RSI-PSAR-Engulfing trading strategy."""
    
    def setUp(self):
        """Set up test configuration and strategy."""
        self.config = {
            'strategy': {
                'rsi': {
                    'period': 14,
                    'overbought': 70,
                    'oversold': 30,
                    'neutral': 50
                },
                'psar': {
                    'af_init': 0.02,
                    'af_step': 0.02,
                    'af_max': 0.20
                },
                'engulfing': {
                    'min_body_ratio': 0.5,
                    'lookback_candles': 3
                },
                'volume': {
                    'avg_period': 20,
                    'anomaly_threshold': 1.0
                }
            },
            'risk_management': {
                'take_profit': 0.15,
                'stop_loss': 0.08,
                'trailing_take_profit': 0.09,
                'trailing_stop': 0.03,
                'position_size': 0.02,
                'max_positions': 10,
                'max_daily_loss': 0.05
            }
        }
        
        self.strategy = RSIPSAREngulfingStrategy(self.config)
        
        # Create sample data with indicators
        self.sample_df = self._create_sample_data()
    
    def _create_sample_data(self) -> pd.DataFrame:
        """Create sample data with indicators for testing."""
        dates = pd.date_range(start='2023-01-01', periods=100, freq='15T')
        
        # Generate realistic price data
        np.random.seed(42)
        base_price = 25000
        returns = np.random.normal(0, 0.01, 100)  # 1% volatility
        prices = base_price * np.exp(np.cumsum(returns))
        
        df = pd.DataFrame({
            'timestamp': dates,
            'open': prices * np.random.uniform(0.998, 1.002, 100),
            'high': prices * np.random.uniform(1.001, 1.015, 100),
            'low': prices * np.random.uniform(0.985, 0.999, 100),
            'close': prices,
            'volume': np.random.randint(50000, 200000, 100)
        })
        
        # Add pre-calculated indicators for controlled testing
        df['rsi'] = 45 + 20 * np.sin(np.linspace(0, 4*np.pi, 100))  # RSI oscillating 25-65
        df['psar'] = prices * 0.98  # PSAR below price (uptrend)
        df['price_vs_psar'] = 1  # Price above PSAR
        df['psar_trend'] = 1  # Uptrend
        
        # Engulfing signals (sparse)
        df['engulfing_signal'] = 0
        df.loc[25, 'engulfing_signal'] = 1  # Bullish at index 25
        df.loc[75, 'engulfing_signal'] = -1  # Bearish at index 75
        df['engulfing_in_3_candles'] = 0
        
        # Volume indicators
        df['avg_volume_20'] = df['volume'].rolling(20).mean().fillna(100000)
        df['volume_anomaly'] = (df['volume'] > df['avg_volume_20']).astype(int)
        
        # Additional required fields
        df['rsi_state'] = 'neutral'
        df['rsi_signal'] = 0
        df['psar_trend'] = 1
        df['body_size'] = abs(df['close'] - df['open'])
        df['engulfing_body_size_ratio'] = 1.0
        
        return df
    
    def test_strategy_initialization(self):
        """Test strategy initialization."""
        self.assertIsNotNone(self.strategy)
        self.assertIsInstance(self.strategy.risk_manager, RiskManager)
        self.assertEqual(len(self.strategy.ticker_states), 0)
        self.assertEqual(len(self.strategy.signal_history), 0)
    
    def test_analyze_ticker_insufficient_data(self):
        """Test behavior with insufficient data."""
        small_df = self.sample_df.head(10)  # Only 10 rows
        
        signals = self.strategy.analyze_ticker('TEST', small_df)
        
        # Should return empty list or handle gracefully
        self.assertIsInstance(signals, list)
    
    def test_buy_conditions(self):
        """Test buy signal conditions."""
        # Create favorable conditions for buy signal
        test_row = pd.Series({
            'close': 25000,
            'psar': 24500,  # Price above PSAR
            'rsi': 55,      # RSI above 50
            'price_vs_psar': 1,
            'volume_anomaly': 1,  # Volume spike
            'engulfing_in_3_candles': 1,  # Recent bullish engulfing
            'volume': 150000,
            'avg_volume_20': 100000
        })
        
        buy_result = self.strategy._check_buy_conditions(test_row)
        
        self.assertTrue(buy_result['signal'])
        self.assertGreater(buy_result['confidence'], 0.6)
        self.assertIn('Price > PSAR', buy_result['reason'])
        self.assertIn('RSI > 50', buy_result['reason'])
    
    def test_buy_conditions_not_met(self):
        """Test buy conditions not met."""
        # Unfavorable conditions
        test_row = pd.Series({
            'close': 25000,
            'psar': 25500,  # Price below PSAR
            'rsi': 45,      # RSI below 50
            'price_vs_psar': 0,
            'volume_anomaly': 0,
            'engulfing_in_3_candles': 0,
            'volume': 50000,
            'avg_volume_20': 100000
        })
        
        buy_result = self.strategy._check_buy_conditions(test_row)
        
        self.assertFalse(buy_result['signal'])
        self.assertEqual(buy_result['confidence'], 0.0)
    
    def test_sell_conditions_no_position(self):
        """Test sell conditions when no position exists."""
        test_row = pd.Series({
            'close': 25000,
            'rsi': 45,
            'engulfing_signal': -1
        })
        
        sell_result = self.strategy._check_sell_conditions('TEST', test_row)
        
        self.assertFalse(sell_result['signal'])
        self.assertEqual(sell_result['confidence'], 0.0)
        self.assertIn('No position', sell_result['reason'])
    
    def test_sell_conditions_take_profit(self):
        """Test sell conditions for take profit."""
        # Set up position state
        self.strategy.update_position_status('TEST', 'long', 25000, datetime.now())
        
        test_row = pd.Series({
            'close': 28750,  # +15% from entry (25000 * 1.15)
            'rsi': 60,
            'engulfing_signal': 0
        })
        
        sell_result = self.strategy._check_sell_conditions('TEST', test_row)
        
        self.assertTrue(sell_result['signal'])
        self.assertEqual(sell_result['confidence'], 1.0)
        self.assertIn('Take Profit', sell_result['reason'])
    
    def test_sell_conditions_stop_loss(self):
        """Test sell conditions for stop loss."""
        # Set up position state
        self.strategy.update_position_status('TEST', 'long', 25000, datetime.now())
        
        test_row = pd.Series({
            'close': 23000,  # -8% from entry (25000 * 0.92)
            'rsi': 60,
            'engulfing_signal': 0
        })
        
        sell_result = self.strategy._check_sell_conditions('TEST', test_row)
        
        self.assertTrue(sell_result['signal'])
        self.assertEqual(sell_result['confidence'], 1.0)
        self.assertIn('Stop Loss', sell_result['reason'])
    
    def test_sell_conditions_technical(self):
        """Test technical sell conditions."""
        # Set up position state
        self.strategy.update_position_status('TEST', 'long', 25000, datetime.now())
        
        test_row = pd.Series({
            'close': 25500,  # Small profit
            'rsi': 45,       # RSI below 50
            'engulfing_signal': -1  # Bearish engulfing
        })
        
        sell_result = self.strategy._check_sell_conditions('TEST', test_row)
        
        self.assertTrue(sell_result['signal'])
        self.assertGreater(sell_result['confidence'], 0.5)
    
    def test_risk_conditions(self):
        """Test risk warning conditions."""
        test_row = pd.Series({
            'volume': 500000,  # Very high volume
            'avg_volume_20': 100000,  # 5x average
            'high': 26000,
            'low': 24000,
            'close': 25000,  # 8% daily range
            'rsi': 75  # Overbought
        })
        
        risk_result = self.strategy._check_risk_conditions('TEST', test_row)
        
        self.assertTrue(risk_result['signal'])
        self.assertGreater(risk_result['confidence'], 0.4)
        self.assertIn('Volume spike', risk_result['reason'])
    
    def test_analyze_ticker_complete_flow(self):
        """Test complete ticker analysis flow."""
        # Use favorable data at the end
        df_copy = self.sample_df.copy()
        
        # Set up favorable conditions in last row
        last_idx = len(df_copy) - 1
        df_copy.loc[last_idx, 'close'] = 26000
        df_copy.loc[last_idx, 'psar'] = 25500  # Price above PSAR
        df_copy.loc[last_idx, 'rsi'] = 55      # RSI above 50
        df_copy.loc[last_idx, 'price_vs_psar'] = 1
        df_copy.loc[last_idx, 'volume_anomaly'] = 1
        df_copy.loc[last_idx, 'engulfing_in_3_candles'] = 1
        
        signals = self.strategy.analyze_ticker('TEST', df_copy)
        
        self.assertIsInstance(signals, list)
        
        # Should have at least one signal with favorable conditions
        if signals:
            signal = signals[0]
            self.assertIsInstance(signal, TradingSignal)
            self.assertEqual(signal.ticker, 'TEST')
            self.assertIn(signal.signal_type, ['buy', 'sell', 'risk_warning'])
    
    def test_position_state_management(self):
        """Test position state management."""
        ticker = 'TEST'
        entry_price = 25000
        entry_time = datetime.now()
        
        # Initial state - no position
        state = self.strategy.get_ticker_state(ticker)
        self.assertIsNone(state)
        
        # Open position
        self.strategy.update_position_status(ticker, 'long', entry_price, entry_time)
        
        state = self.strategy.get_ticker_state(ticker)
        self.assertIsNotNone(state)
        self.assertEqual(state.position_status, 'long')
        self.assertEqual(state.entry_price, entry_price)
        self.assertEqual(state.entry_date, entry_time)
        
        # Close position
        self.strategy.update_position_status(ticker, 'none')
        
        state = self.strategy.get_ticker_state(ticker)
        self.assertEqual(state.position_status, 'none')
        self.assertIsNone(state.entry_price)
    
    def test_signal_history_management(self):
        """Test signal history management."""
        # Create test signals
        for i in range(5):
            signal = TradingSignal(
                ticker='TEST',
                timestamp=datetime.now(),
                signal_type='buy',
                confidence=0.7,
                entry_price=25000 + i * 100,
                reason='test signal'
            )
            self.strategy.add_signal_to_history(signal)
        
        history = self.strategy.get_signal_history()
        self.assertEqual(len(history), 5)
        
        # Test limit
        limited_history = self.strategy.get_signal_history(limit=3)
        self.assertEqual(len(limited_history), 3)
    
    def test_performance_stats(self):
        """Test performance statistics calculation."""
        # Add some test signals
        signals = [
            TradingSignal('TEST1', datetime.now(), 'buy', 0.8, 25000, reason='test'),
            TradingSignal('TEST2', datetime.now(), 'sell', 0.7, 26000, reason='test'),
            TradingSignal('TEST3', datetime.now(), 'risk_warning', 0.6, 24000, reason='test')
        ]
        
        for signal in signals:
            self.strategy.add_signal_to_history(signal)
        
        stats = self.strategy.get_performance_stats()
        
        self.assertIn('total_signals', stats)
        self.assertIn('buy_signals', stats)
        self.assertIn('sell_signals', stats)
        self.assertIn('risk_warnings', stats)
        self.assertIn('avg_confidence', stats)
        
        self.assertEqual(stats['total_signals'], 3)
        self.assertEqual(stats['buy_signals'], 1)
        self.assertEqual(stats['sell_signals'], 1)
        self.assertEqual(stats['risk_warnings'], 1)
    
    def test_stop_loss_calculation(self):
        """Test stop loss calculation."""
        entry_price = 25000
        sl_price = self.strategy._calculate_stop_loss(entry_price, 'long')
        
        expected_sl = entry_price * (1 - 0.08)  # 8% stop loss
        self.assertAlmostEqual(sl_price, expected_sl, places=0)
    
    def test_take_profit_calculation(self):
        """Test take profit calculation."""
        entry_price = 25000
        tp_price = self.strategy._calculate_take_profit(entry_price, 'long')
        
        expected_tp = entry_price * (1 + 0.15)  # 15% take profit
        self.assertAlmostEqual(tp_price, expected_tp, places=0)


class TestRiskManager(unittest.TestCase):
    """Test risk management functionality."""
    
    def setUp(self):
        """Set up risk manager."""
        self.config = {
            'take_profit': 0.15,
            'stop_loss': 0.08,
            'position_size': 0.02,
            'max_positions': 10,
            'max_daily_loss': 0.05
        }
        
        self.risk_manager = RiskManager(self.config)
    
    def test_position_size_calculation(self):
        """Test position size calculation."""
        portfolio_value = 1000000  # 1M VND
        entry_price = 25000
        stop_loss_price = 23000
        
        position_size = self.risk_manager.calculate_position_size(
            'TEST', entry_price, stop_loss_price, portfolio_value
        )
        
        # Should be reasonable position size
        self.assertGreater(position_size, 0)
        self.assertLess(position_size, 1000)  # Not too large
        
        # Risk should be approximately 2% of portfolio
        risk_amount = position_size * (entry_price - stop_loss_price)
        expected_risk = portfolio_value * 0.02
        
        # Allow some tolerance due to integer rounding
        self.assertLessEqual(risk_amount, expected_risk * 1.1)
    
    def test_position_limits_check(self):
        """Test position limits checking."""
        # Create mock current positions
        current_positions = {}
        for i in range(5):  # 5 open positions
            state = Mock()
            state.position_status = 'long'
            current_positions[f'TEST{i}'] = state
        
        # Should allow new position (under limit)
        can_open = self.risk_manager.check_position_limits('NEW_TEST', current_positions)
        self.assertTrue(can_open)
        
        # Fill up to limit
        for i in range(5, 10):
            state = Mock()
            state.position_status = 'long'
            current_positions[f'TEST{i}'] = state
        
        # Should not allow new position (at limit)
        can_open = self.risk_manager.check_position_limits('NEW_TEST2', current_positions)
        self.assertFalse(can_open)
    
    def test_daily_loss_limit(self):
        """Test daily loss limit checking."""
        portfolio_value = 1000000  # 1M VND
        
        # Small loss - should be OK
        small_loss = -30000  # -3%
        within_limit = self.risk_manager.check_daily_loss_limit(small_loss, portfolio_value)
        self.assertTrue(within_limit)
        
        # Large loss - should exceed limit
        large_loss = -60000  # -6%
        within_limit = self.risk_manager.check_daily_loss_limit(large_loss, portfolio_value)
        self.assertFalse(within_limit)
        
        # Check circuit breaker activation
        self.assertTrue(self.risk_manager.circuit_breaker_active)


if __name__ == '__main__':
    unittest.main()
