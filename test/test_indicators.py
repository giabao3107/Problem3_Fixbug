"""
Unit tests for technical indicators.
"""

import unittest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from utils.indicators import TechnicalIndicators, IndicatorValidator


class TestTechnicalIndicators(unittest.TestCase):
    """Test technical indicators calculations."""
    
    def setUp(self):
        """Set up test data."""
        # Generate sample OHLCV data
        dates = pd.date_range(start='2023-01-01', periods=100, freq='15T')
        
        # Random walk price data
        np.random.seed(42)
        base_price = 25000
        returns = np.random.normal(0, 0.02, 100)
        prices = base_price * np.exp(np.cumsum(returns))
        
        self.sample_data = pd.DataFrame({
            'timestamp': dates,
            'open': prices * np.random.uniform(0.995, 1.005, 100),
            'high': prices * np.random.uniform(1.001, 1.02, 100),
            'low': prices * np.random.uniform(0.98, 0.999, 100),
            'close': prices,
            'volume': np.random.randint(10000, 100000, 100)
        })
        
        # Ensure high >= low >= close logic
        for i in range(len(self.sample_data)):
            row = self.sample_data.iloc[i]
            high = max(row['open'], row['high'], row['close'])
            low = min(row['open'], row['low'], row['close'])
            self.sample_data.loc[i, 'high'] = high
            self.sample_data.loc[i, 'low'] = low
    
    def test_rsi_calculation(self):
        """Test RSI calculation."""
        rsi_result = TechnicalIndicators.rsi(self.sample_data['close'], period=14)
        
        # Check basic properties
        self.assertIsNotNone(rsi_result.values)
        self.assertEqual(len(rsi_result.values), len(self.sample_data))
        
        # RSI should be between 0 and 100 (excluding NaN)
        valid_rsi = rsi_result.values[~np.isnan(rsi_result.values)]
        self.assertTrue(np.all((valid_rsi >= 0) & (valid_rsi <= 100)))
        
        # Should have some NaN values at the beginning
        self.assertTrue(np.any(np.isnan(rsi_result.values[:14])))
        
        # Should have valid values after the period
        self.assertTrue(np.any(~np.isnan(rsi_result.values[20:])))
        
        # Check metadata
        self.assertIn('period', rsi_result.metadata)
        self.assertEqual(rsi_result.metadata['period'], 14)
    
    def test_psar_calculation(self):
        """Test PSAR calculation."""
        psar_result = TechnicalIndicators.parabolic_sar(
            self.sample_data['high'],
            self.sample_data['low'], 
            self.sample_data['close']
        )
        
        # Check basic properties
        self.assertIsNotNone(psar_result.values)
        self.assertEqual(len(psar_result.values), len(self.sample_data))
        
        # PSAR values should be positive and reasonable
        valid_psar = psar_result.values[~np.isnan(psar_result.values)]
        self.assertTrue(np.all(valid_psar > 0))
        
        # Signals should be -1 or 1
        valid_signals = psar_result.signals[~np.isnan(psar_result.signals)]
        self.assertTrue(np.all((valid_signals == -1) | (valid_signals == 1)))
        
        # Check metadata
        self.assertIn('af_init', psar_result.metadata)
        self.assertEqual(psar_result.metadata['af_init'], 0.02)
    
    def test_engulfing_pattern(self):
        """Test engulfing pattern detection."""
        engulfing_result = TechnicalIndicators.engulfing_pattern(
            self.sample_data['open'],
            self.sample_data['high'],
            self.sample_data['low'],
            self.sample_data['close']
        )
        
        # Check basic properties
        self.assertIsNotNone(engulfing_result.values)
        self.assertEqual(len(engulfing_result.values), len(self.sample_data))
        
        # Signals should be -1, 0, or 1
        self.assertTrue(np.all((engulfing_result.values >= -1) & (engulfing_result.values <= 1)))
        
        # Should be mostly zeros (patterns are rare)
        zero_count = np.sum(engulfing_result.values == 0)
        self.assertGreater(zero_count, len(self.sample_data) * 0.8)  # At least 80% zeros
        
        # Check metadata
        self.assertIn('min_body_ratio', engulfing_result.metadata)
    
    def test_volume_analysis(self):
        """Test volume analysis."""
        volume_result = TechnicalIndicators.volume_analysis(
            self.sample_data['volume'],
            avg_period=20
        )
        
        # Check basic properties
        self.assertIsNotNone(volume_result.values)  # Average volumes
        self.assertEqual(len(volume_result.values), len(self.sample_data))
        
        # Average volumes should be positive
        valid_avg_vol = volume_result.values[~np.isnan(volume_result.values)]
        self.assertTrue(np.all(valid_avg_vol > 0))
        
        # Anomaly signals should be 0 or 1
        self.assertTrue(np.all((volume_result.signals == 0) | (volume_result.signals == 1)))
        
        # Check metadata
        self.assertIn('avg_period', volume_result.metadata)
        self.assertEqual(volume_result.metadata['avg_period'], 20)
    
    def test_calculate_all_indicators(self):
        """Test calculation of all indicators together."""
        result_df = TechnicalIndicators.calculate_all_indicators(self.sample_data)
        
        # Should have all original columns
        for col in self.sample_data.columns:
            self.assertIn(col, result_df.columns)
        
        # Should have indicator columns
        expected_indicators = [
            'rsi', 'rsi_signal', 'psar', 'psar_trend', 'price_vs_psar',
            'engulfing_signal', 'engulfing_in_3_candles',
            'avg_volume_20', 'volume_anomaly', 'rsi_state'
        ]
        
        for indicator in expected_indicators:
            self.assertIn(indicator, result_df.columns, f"Missing indicator: {indicator}")
        
        # Check data integrity
        self.assertEqual(len(result_df), len(self.sample_data))
        
        # RSI state should be categorical
        valid_states = ['overbought', 'oversold', 'neutral', 'trending_up', 'trending_down']
        unique_states = result_df['rsi_state'].dropna().unique()
        for state in unique_states:
            self.assertIn(state, valid_states)
    
    def test_insufficient_data(self):
        """Test handling of insufficient data."""
        # Create small dataset
        small_data = self.sample_data.head(5)
        
        # RSI with insufficient data
        rsi_result = TechnicalIndicators.rsi(small_data['close'], period=14)
        
        # Should return NaN values but not crash
        self.assertEqual(len(rsi_result.values), len(small_data))
        
        # Most values should be NaN
        nan_count = np.sum(np.isnan(rsi_result.values))
        self.assertGreater(nan_count, 0)
    
    def test_edge_cases(self):
        """Test edge cases."""
        # All same prices (no volatility)
        flat_prices = pd.Series([25000] * 50)
        rsi_result = TechnicalIndicators.rsi(flat_prices, period=14)
        
        # RSI should be around 50 for flat prices (after initial period)
        valid_rsi = rsi_result.values[~np.isnan(rsi_result.values)]
        if len(valid_rsi) > 0:
            # For flat prices, RSI typically converges to 50
            self.assertTrue(np.all((valid_rsi >= 45) & (valid_rsi <= 55)))
        
        # Zero volumes
        zero_volumes = pd.Series([0] * 50)
        volume_result = TechnicalIndicators.volume_analysis(zero_volumes, avg_period=10)
        
        # Should handle gracefully
        self.assertEqual(len(volume_result.values), 50)


class TestIndicatorValidator(unittest.TestCase):
    """Test indicator validation functions."""
    
    def test_rsi_validation(self):
        """Test RSI validation."""
        # Valid RSI values
        valid_rsi = np.array([30, 50, 70, 45, 65, np.nan])
        validation = IndicatorValidator.validate_rsi(valid_rsi)
        
        self.assertTrue(validation['values_in_range'])
        self.assertTrue(validation['no_infinite_values'])
        self.assertTrue(validation['has_valid_values'])
        
        # Invalid RSI values
        invalid_rsi = np.array([150, -10, 50])
        validation = IndicatorValidator.validate_rsi(invalid_rsi)
        
        self.assertFalse(validation['values_in_range'])
    
    def test_psar_validation(self):
        """Test PSAR validation."""
        prices = np.array([25000, 25500, 24800, 25200, 25600])
        psar_values = np.array([24000, 24200, 24500, 24800, 25000])
        
        validation = IndicatorValidator.validate_psar(psar_values, prices)
        
        self.assertTrue(validation['no_infinite_values'])
        self.assertTrue(validation['has_valid_values'])
        self.assertTrue(validation['reasonable_range'])
    
    def test_engulfing_validation(self):
        """Test engulfing pattern validation."""
        # Valid signals
        valid_signals = np.array([-1, 0, 1, 0, -1, 0])
        validation = IndicatorValidator.validate_engulfing(valid_signals)
        
        self.assertTrue(validation['valid_signal_range'])
        self.assertTrue(validation['integer_signals'])
        self.assertTrue(validation['has_patterns'])
        
        # Invalid signals
        invalid_signals = np.array([2, 0.5, -1])
        validation = IndicatorValidator.validate_engulfing(invalid_signals)
        
        self.assertFalse(validation['valid_signal_range'])
        self.assertFalse(validation['integer_signals'])


if __name__ == '__main__':
    unittest.main()
