"""
Unit tests for FiinQuant adapter.
"""

import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
import asyncio

from utils.fiinquant_adapter import FiinQuantAdapter, MarketDataPoint


class TestMarketDataPoint(unittest.TestCase):
    """Test MarketDataPoint data structure."""
    
    def test_market_data_point_creation(self):
        """Test creation of MarketDataPoint."""
        data_point = MarketDataPoint(
            ticker='ACB',
            timestamp=datetime.now(),
            open=25000,
            high=25500,
            low=24800,
            close=25200,
            volume=100000,
            change=200,
            change_percent=0.8
        )
        
        self.assertEqual(data_point.ticker, 'ACB')
        self.assertIsInstance(data_point.timestamp, datetime)
        self.assertEqual(data_point.open, 25000)
        self.assertEqual(data_point.volume, 100000)
        self.assertEqual(data_point.change_percent, 0.8)




@patch('realtime_alert_system.utils.fiinquant_adapter.FIINQUANT_AVAILABLE', True)
class TestFiinQuantAdapter(unittest.TestCase):
    """Test real FiinQuant adapter (mocked)."""
    
    def setUp(self):
        """Set up adapter with mocked dependencies."""
        self.adapter = FiinQuantAdapter(
            username='test_user',
            password='test_pass',
            retry_attempts=2,
            retry_delay=1
        )
    
    def test_session_validation(self):
        """Test session validation logic."""
        # Initially no valid session
        self.assertFalse(self.adapter._is_session_valid())
        
        # Set session time
        self.adapter.session_created_at = datetime.now()
        self.adapter.is_logged_in = True
        
        # Should be valid
        self.assertTrue(self.adapter._is_session_valid())
        
        # Old session should be invalid
        self.adapter.session_created_at = datetime.now() - timedelta(minutes=10)
        self.assertFalse(self.adapter._is_session_valid())
    
    @patch('realtime_alert_system.utils.fiinquant_adapter.FiinSession')
    def test_login_success(self, mock_session_class):
        """Test successful login."""
        # Mock successful login
        mock_session = Mock()
        mock_session_class.return_value.login.return_value = mock_session
        
        success = self.adapter.login()
        
        self.assertTrue(success)
        self.assertTrue(self.adapter.is_logged_in)
        self.assertIsNotNone(self.adapter.session_created_at)
        self.assertEqual(self.adapter.client, mock_session)
    
    @patch('realtime_alert_system.utils.fiinquant_adapter.FiinSession')
    def test_login_failure(self, mock_session_class):
        """Test login failure with retries."""
        # Mock login failure
        mock_session_class.return_value.login.side_effect = Exception("Login failed")
        
        success = self.adapter.login()
        
        self.assertFalse(success)
        self.assertFalse(self.adapter.is_logged_in)
        
        # Should have tried multiple times
        self.assertEqual(mock_session_class.return_value.login.call_count, 2)
    
    @patch('realtime_alert_system.utils.fiinquant_adapter.FiinSession')
    def test_fetch_historical_data_success(self, mock_session_class):
        """Test successful historical data fetching."""
        # Setup mock session
        mock_session = Mock()
        mock_fetch_data = Mock()
        mock_fetch_data.get_data.return_value = pd.DataFrame({
            'open': [25000, 25100],
            'high': [25200, 25300],
            'low': [24800, 24900],
            'close': [25100, 25200],
            'volume': [100000, 120000]
        })
        
        mock_session.Fetch_Trading_Data.return_value = mock_fetch_data
        mock_session_class.return_value.login.return_value = mock_session
        
        # Set up adapter
        self.adapter.client = mock_session
        self.adapter.is_logged_in = True
        self.adapter.session_created_at = datetime.now()
        
        # Fetch data
        df = self.adapter.fetch_historical_data(['ACB'], timeframe='15m', period=100)
        
        self.assertIsInstance(df, pd.DataFrame)
        self.assertGreater(len(df), 0)
        self.assertIn('close', df.columns)
    
    def test_market_hours(self):
        """Test market hours checking."""
        # Test different times
        with patch('realtime_alert_system.utils.fiinquant_adapter.datetime') as mock_datetime:
            # Market hours (10 AM on weekday)
            mock_datetime.now.return_value = datetime(2023, 6, 1, 10, 0, 0)  # Thursday
            self.assertTrue(self.adapter.is_market_open())
            
            # Outside market hours (8 PM on weekday)
            mock_datetime.now.return_value = datetime(2023, 6, 1, 20, 0, 0)  # Thursday
            self.assertFalse(self.adapter.is_market_open())
            
            # Weekend
            mock_datetime.now.return_value = datetime(2023, 6, 3, 10, 0, 0)  # Saturday
            self.assertFalse(self.adapter.is_market_open())
    
    def test_health_check(self):
        """Test comprehensive health check."""
        health = self.adapter.health_check()
        
        self.assertIsInstance(health, dict)
        
        # Check required fields
        required_fields = [
            'fiinquant_available', 'logged_in', 'session_valid',
            'stream_active', 'market_open', 'cache_size'
        ]
        
        for field in required_fields:
            self.assertIn(field, health)
    
    def test_cache_functionality(self):
        """Test data caching."""
        # Mock successful data fetch
        with patch.object(self.adapter, 'fetch_historical_data') as mock_fetch:
            mock_df = pd.DataFrame({'close': [25000], 'volume': [100000]})
            mock_fetch.return_value = mock_df
            
            # First call - should fetch data
            result1 = self.adapter.get_latest_data('ACB', use_cache=True)
            self.assertEqual(mock_fetch.call_count, 1)
            
            # Second call - should use cache
            result2 = self.adapter.get_latest_data('ACB', use_cache=True)
            self.assertEqual(mock_fetch.call_count, 1)  # No additional call
    
    def test_cleanup(self):
        """Test cleanup on destruction."""
        # Start a mock stream
        self.adapter.stream_active = True
        
        # Mock stop method
        with patch.object(self.adapter, 'stop_realtime_stream') as mock_stop:
            # Trigger cleanup
            self.adapter.__del__()
            
            # Should have called stop
            mock_stop.assert_called_once()


class TestErrorHandling(unittest.TestCase):
    """Test error handling scenarios."""
    
    @patch('realtime_alert_system.utils.fiinquant_adapter.FiinSession')
    def test_network_errors(self, mock_session_class):
        """Test handling of network errors."""
        # Mock network error
        mock_session_class.return_value.login.side_effect = ConnectionError("Network error")
        
        adapter = FiinQuantAdapter('test_user', 'test_pass')
        
        # Should handle gracefully
        with self.assertRaises(ConnectionError):
            adapter.login()
    
    @patch('realtime_alert_system.utils.fiinquant_adapter.FiinSession')
    def test_invalid_credentials(self, mock_session_class):
        """Test handling of invalid credentials."""
        # Mock invalid credentials
        mock_session_class.return_value.login.side_effect = Exception("Invalid credentials")
        
        adapter = FiinQuantAdapter('invalid_user', 'invalid_pass')
        
        # Should return False on login failure
        success = adapter.login()
        self.assertFalse(success)
    
    @patch('realtime_alert_system.utils.fiinquant_adapter.FiinSession')
    def test_empty_data_handling(self, mock_session_class):
        """Test handling of empty data responses."""
        # Setup mocks
        mock_session = Mock()
        mock_fetch_data = Mock()
        mock_fetch_data.get_data.return_value = pd.DataFrame()
        mock_session.Fetch_Trading_Data.return_value = mock_fetch_data
        mock_session_class.return_value.login.return_value = mock_session
        
        adapter = FiinQuantAdapter('test_user', 'test_pass')
        adapter.client = mock_session
        adapter.is_logged_in = True
        adapter.session_created_at = datetime.now()
        
        df = adapter.fetch_historical_data(['ACB'])
        self.assertTrue(df.empty)
    
    def test_invalid_ticker_handling(self):
        """Test handling of invalid tickers."""
        adapter = FiinQuantAdapter('test_user', 'test_pass')
        
        # Should handle invalid tickers gracefully in get_latest_data
        with patch.object(adapter, 'fetch_historical_data', return_value=pd.DataFrame()):
            data_point = adapter.get_latest_data('INVALID_TICKER')
            self.assertIsNone(data_point)


if __name__ == '__main__':
    unittest.main()
