import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from utils.fiinquant_adapter import FiinQuantAdapter, MarketDataPoint


class TestFiinQuantAdapter:
    """Test cases for FiinQuantAdapter."""
    
    def test_init_with_valid_credentials(self, mock_config):
        """Test adapter initialization with valid credentials."""
        adapter = FiinQuantAdapter(
            username=mock_config['fiinquant']['username'],
            password=mock_config['fiinquant']['password']
        )
        
        assert adapter.username == 'test_user'
        assert adapter.password == 'test_pass'
        assert adapter.retry_attempts == 3
        assert adapter.retry_delay == 5
        assert adapter.cache_duration == 300
        assert not adapter.is_logged_in
        assert adapter.client is None
    
    def test_init_with_cache_manager(self, mock_config, mock_cache_manager):
        """Test adapter initialization with cache manager."""
        with patch('utils.fiinquant_adapter.get_cache_manager', return_value=mock_cache_manager):
            adapter = FiinQuantAdapter(
                username=mock_config['fiinquant']['username'],
                password=mock_config['fiinquant']['password']
            )
            
            assert adapter.cache_manager is not None
    
    @patch('utils.fiinquant_adapter.FIINQUANT_AVAILABLE', True)
    @patch('utils.fiinquant_adapter.FiinSession')
    def test_login_success(self, mock_fiinsession, mock_config):
        """Test successful login."""
        # Setup mock
        mock_client = Mock()
        mock_client.login.return_value = True
        mock_fiinsession.return_value = mock_client
        
        adapter = FiinQuantAdapter(
            username=mock_config['fiinquant']['username'],
            password=mock_config['fiinquant']['password']
        )
        
        # Test login
        result = adapter.login()
        
        assert result is True
        assert adapter.is_logged_in is True
        assert adapter.client is not None
        assert adapter.session_created_at is not None
    
    @patch('utils.fiinquant_adapter.FIINQUANT_AVAILABLE', True)
    @patch('utils.fiinquant_adapter.FiinSession')
    def test_login_failure(self, mock_fiinsession, mock_config):
        """Test login failure."""
        # Setup mock to fail
        mock_client = Mock()
        mock_client.login.side_effect = Exception("Login failed")
        mock_fiinsession.return_value = mock_client
        
        adapter = FiinQuantAdapter(
            username=mock_config['fiinquant']['username'],
            password=mock_config['fiinquant']['password']
        )
        
        # Test login failure
        result = adapter.login()
        
        assert result is False
        assert adapter.is_logged_in is False
    
    def test_session_validity_check(self, mock_config):
        """Test session validity checking."""
        adapter = FiinQuantAdapter(
            username=mock_config['fiinquant']['username'],
            password=mock_config['fiinquant']['password']
        )
        
        # Test with no session
        assert not adapter._is_session_valid()
        
        # Test with recent session
        adapter.session_created_at = datetime.now()
        assert adapter._is_session_valid()
        
        # Test with expired session
        adapter.session_created_at = datetime.now() - timedelta(seconds=400)
        assert not adapter._is_session_valid()
    
    def test_get_latest_data_with_cache(self, mock_config, mock_cache_manager, sample_ohlcv_data):
        """Test getting latest data with caching."""
        adapter = FiinQuantAdapter(
            username=mock_config['fiinquant']['username'],
            password=mock_config['fiinquant']['password']
        )
        adapter.cache_manager = mock_cache_manager
        
        # Setup cache to return data
        cached_data = MarketDataPoint(
            ticker='VIC',
            timestamp=datetime.now(),
            open=100.0,
            high=105.0,
            low=95.0,
            close=103.0,
            volume=1000000,
            change=3.0,
            change_percent=3.0
        )
        mock_cache_manager.get.return_value = cached_data
        
        result = adapter.get_latest_data('VIC')
        
        assert result == cached_data
        mock_cache_manager.get.assert_called_once()
    
    def test_get_latest_data_no_cache(self, mock_config, sample_ohlcv_data):
        """Test getting latest data without cache."""
        adapter = FiinQuantAdapter(
            username=mock_config['fiinquant']['username'],
            password=mock_config['fiinquant']['password']
        )
        
        # Mock fetch_historical_data to return sample data
        with patch.object(adapter, 'fetch_historical_data', return_value=sample_ohlcv_data):
            result = adapter.get_latest_data('VIC', use_cache=False)
            
            assert result is not None
            assert result.ticker == 'VIC'
            assert isinstance(result.close, float)
            assert result.volume > 0
    
    def test_fetch_historical_data_with_cache(self, mock_config, mock_cache_manager, sample_ohlcv_data):
        """Test fetching historical data with caching."""
        adapter = FiinQuantAdapter(
            username=mock_config['fiinquant']['username'],
            password=mock_config['fiinquant']['password']
        )
        adapter.cache_manager = mock_cache_manager
        
        # Setup cache to return data
        mock_cache_manager.get.return_value = sample_ohlcv_data
        
        result = adapter.fetch_historical_data(['VIC'], period=30)
        
        assert not result.empty
        assert len(result) == len(sample_ohlcv_data)
        mock_cache_manager.get.assert_called_once()
    
    def test_health_check(self, mock_config, mock_cache_manager):
        """Test health check functionality."""
        adapter = FiinQuantAdapter(
            username=mock_config['fiinquant']['username'],
            password=mock_config['fiinquant']['password']
        )
        adapter.cache_manager = mock_cache_manager
        adapter.is_logged_in = True
        adapter.session_created_at = datetime.now()
        
        # Setup cache stats
        mock_cache_manager.get_stats.return_value = {
            'hits': 100,
            'misses': 20,
            'hit_ratio': 0.83
        }
        
        health = adapter.health_check()
        
        assert health['logged_in'] is True
        assert health['session_valid'] is True
        assert health['fiinquant_available'] is not None
        assert health['advanced_cache_available'] is True
        assert 'cache_stats' in health
    
    def test_clear_cache(self, mock_config, mock_cache_manager):
        """Test cache clearing functionality."""
        adapter = FiinQuantAdapter(
            username=mock_config['fiinquant']['username'],
            password=mock_config['fiinquant']['password']
        )
        adapter.cache_manager = mock_cache_manager
        
        # Add some legacy cache data
        adapter.data_cache['test_key'] = {'data': 'test'}
        adapter.cache_timestamps['test_key'] = datetime.now()
        
        # Test clearing all cache
        result = adapter.clear_cache()
        
        assert result is True
        assert len(adapter.data_cache) == 0
        assert len(adapter.cache_timestamps) == 0
        mock_cache_manager.clear.assert_called_once()
    
    def test_clear_cache_with_pattern(self, mock_config, mock_cache_manager):
        """Test cache clearing with pattern."""
        adapter = FiinQuantAdapter(
            username=mock_config['fiinquant']['username'],
            password=mock_config['fiinquant']['password']
        )
        adapter.cache_manager = mock_cache_manager
        
        # Add some legacy cache data
        adapter.data_cache['latest_data:VIC'] = {'data': 'test1'}
        adapter.data_cache['historical_data:VHM'] = {'data': 'test2'}
        adapter.cache_timestamps['latest_data:VIC'] = datetime.now()
        adapter.cache_timestamps['historical_data:VHM'] = datetime.now()
        
        # Setup mock return value
        mock_cache_manager.delete_pattern.return_value = 5
        
        # Test clearing with pattern
        result = adapter.clear_cache('latest_data:*')
        
        assert result is True
        assert 'latest_data:VIC' not in adapter.data_cache
        assert 'historical_data:VHM' in adapter.data_cache  # Should remain
        mock_cache_manager.delete_pattern.assert_called_once_with('latest_data:*')
    
    def test_market_data_point_creation(self):
        """Test MarketDataPoint creation and validation."""
        data_point = MarketDataPoint(
            ticker='VIC',
            timestamp=datetime.now(),
            open=100.0,
            high=105.0,
            low=95.0,
            close=103.0,
            volume=1000000,
            change=3.0,
            change_percent=3.0
        )
        
        assert data_point.ticker == 'VIC'
        assert data_point.open == 100.0
        assert data_point.high == 105.0
        assert data_point.low == 95.0
        assert data_point.close == 103.0
        assert data_point.volume == 1000000
        assert data_point.change == 3.0
        assert data_point.change_percent == 3.0
    
    @pytest.mark.slow
    def test_realtime_stream_functionality(self, mock_config):
        """Test realtime streaming functionality."""
        adapter = FiinQuantAdapter(
            username=mock_config['fiinquant']['username'],
            password=mock_config['fiinquant']['password']
        )
        
        # Mock callback function
        callback = Mock()
        
        # Test starting stream (should fail without proper setup)
        result = adapter.start_realtime_stream(['VIC'], callback)
        
        # Should fail because not logged in
        assert result is False
        
        # Test stopping stream
        adapter.stop_realtime_stream()
        assert not adapter.stream_active
    
    def test_error_handling_in_fetch_data(self, mock_config):
        """Test error handling in data fetching."""
        adapter = FiinQuantAdapter(
            username=mock_config['fiinquant']['username'],
            password=mock_config['fiinquant']['password']
        )
        
        # Test with empty ticker list
        result = adapter.fetch_historical_data([])
        assert result.empty
        
        # Test get_latest_data with invalid ticker
        result = adapter.get_latest_data('')
        assert result is None
    
    def test_adapter_cleanup(self, mock_config):
        """Test adapter cleanup on destruction."""
        adapter = FiinQuantAdapter(
            username=mock_config['fiinquant']['username'],
            password=mock_config['fiinquant']['password']
        )
        
        # Set up some state
        adapter.stream_active = True
        adapter.stream_thread = Mock()
        
        # Test cleanup
        adapter.__del__()
        
        # Should stop streaming
        assert not adapter.stream_active


@pytest.mark.integration
class TestFiinQuantAdapterIntegration:
    """Integration tests for FiinQuantAdapter."""
    
    @pytest.mark.network
    def test_real_login_attempt(self):
        """Test real login attempt (requires valid credentials)."""
        # This test should be skipped in CI/CD unless credentials are available
        pytest.skip("Requires real FiinQuant credentials")
    
    @pytest.mark.redis
    def test_redis_cache_integration(self, mock_config):
        """Test Redis cache integration."""
        # This test requires Redis to be running
        pytest.skip("Requires Redis server")