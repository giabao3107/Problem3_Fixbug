import pytest
import time
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from utils.cache_manager import CacheManager, cached, get_cache_manager


class TestCacheManager:
    """Test cases for CacheManager class."""
    
    def test_cache_manager_initialization_with_redis(self, mock_redis_client):
        """Test CacheManager initialization with Redis."""
        cache_manager = CacheManager(redis_client=mock_redis_client)
        
        assert cache_manager.redis_client == mock_redis_client
        assert cache_manager.default_ttl == 300
        assert cache_manager.key_prefix == "realtime_alert:"
        assert cache_manager.stats['hits'] == 0
        assert cache_manager.stats['misses'] == 0
    
    def test_cache_manager_initialization_without_redis(self):
        """Test CacheManager initialization without Redis (fallback mode)."""
        cache_manager = CacheManager(redis_client=None)
        
        assert cache_manager.redis_client is None
        assert isinstance(cache_manager.local_cache, dict)
        assert cache_manager.fallback_mode is True
    
    def test_generate_cache_key(self, mock_redis_client):
        """Test cache key generation."""
        cache_manager = CacheManager(redis_client=mock_redis_client)
        
        # Test simple key
        key = cache_manager._generate_cache_key("test", "arg1", "arg2")
        expected = "realtime_alert:test:arg1:arg2"
        assert key == expected
        
        # Test with complex arguments
        key = cache_manager._generate_cache_key("func", {"a": 1}, [1, 2, 3])
        assert key.startswith("realtime_alert:func:")
        assert "a" in key or "1" in key  # Should contain serialized data
    
    def test_set_and_get_with_redis(self, mock_redis_client):
        """Test setting and getting cache with Redis."""
        cache_manager = CacheManager(redis_client=mock_redis_client)
        
        # Mock Redis responses
        mock_redis_client.setex.return_value = True
        mock_redis_client.get.return_value = json.dumps({"result": "test_data"})
        
        # Test set
        result = cache_manager.set("test_key", {"result": "test_data"}, ttl=60)
        assert result is True
        mock_redis_client.setex.assert_called_once()
        
        # Test get
        data = cache_manager.get("test_key")
        assert data == {"result": "test_data"}
        mock_redis_client.get.assert_called_once()
        assert cache_manager.stats['hits'] == 1
    
    def test_get_cache_miss_with_redis(self, mock_redis_client):
        """Test cache miss with Redis."""
        cache_manager = CacheManager(redis_client=mock_redis_client)
        
        # Mock Redis returning None (cache miss)
        mock_redis_client.get.return_value = None
        
        data = cache_manager.get("nonexistent_key")
        assert data is None
        assert cache_manager.stats['misses'] == 1
    
    def test_set_and_get_fallback_mode(self):
        """Test setting and getting cache in fallback mode."""
        cache_manager = CacheManager(redis_client=None)
        
        # Test set
        result = cache_manager.set("test_key", {"result": "test_data"}, ttl=60)
        assert result is True
        
        # Test get (should work immediately)
        data = cache_manager.get("test_key")
        assert data == {"result": "test_data"}
        assert cache_manager.stats['hits'] == 1
    
    def test_fallback_mode_expiration(self):
        """Test cache expiration in fallback mode."""
        cache_manager = CacheManager(redis_client=None)
        
        # Set with very short TTL
        cache_manager.set("test_key", "test_data", ttl=1)
        
        # Should be available immediately
        assert cache_manager.get("test_key") == "test_data"
        
        # Wait for expiration
        time.sleep(1.1)
        
        # Should be expired
        assert cache_manager.get("test_key") is None
        assert cache_manager.stats['misses'] == 1
    
    def test_delete_with_redis(self, mock_redis_client):
        """Test cache deletion with Redis."""
        cache_manager = CacheManager(redis_client=mock_redis_client)
        
        mock_redis_client.delete.return_value = 1
        
        result = cache_manager.delete("test_key")
        assert result is True
        mock_redis_client.delete.assert_called_once_with("realtime_alert:test_key")
    
    def test_delete_fallback_mode(self):
        """Test cache deletion in fallback mode."""
        cache_manager = CacheManager(redis_client=None)
        
        # Set then delete
        cache_manager.set("test_key", "test_data")
        result = cache_manager.delete("test_key")
        
        assert result is True
        assert cache_manager.get("test_key") is None
    
    def test_clear_with_redis(self, mock_redis_client):
        """Test cache clearing with Redis."""
        cache_manager = CacheManager(redis_client=mock_redis_client)
        
        # Mock Redis scan and delete
        mock_redis_client.scan_iter.return_value = ["realtime_alert:key1", "realtime_alert:key2"]
        mock_redis_client.delete.return_value = 2
        
        result = cache_manager.clear(pattern="*")
        assert result == 2
        mock_redis_client.scan_iter.assert_called_once()
        mock_redis_client.delete.assert_called_once()
    
    def test_clear_fallback_mode(self):
        """Test cache clearing in fallback mode."""
        cache_manager = CacheManager(redis_client=None)
        
        # Set some data
        cache_manager.set("key1", "data1")
        cache_manager.set("key2", "data2")
        
        result = cache_manager.clear()
        assert result == 2
        assert len(cache_manager.local_cache) == 0
    
    def test_get_stats(self, mock_redis_client):
        """Test getting cache statistics."""
        cache_manager = CacheManager(redis_client=mock_redis_client)
        
        # Simulate some cache operations
        mock_redis_client.get.return_value = None  # Miss
        cache_manager.get("key1")
        
        mock_redis_client.get.return_value = json.dumps("data")  # Hit
        cache_manager.get("key2")
        
        stats = cache_manager.get_stats()
        
        assert stats['hits'] == 1
        assert stats['misses'] == 1
        assert stats['hit_rate'] == 0.5
        assert 'redis_connected' in stats
        assert 'fallback_mode' in stats
    
    def test_health_check_with_redis(self, mock_redis_client):
        """Test health check with Redis."""
        cache_manager = CacheManager(redis_client=mock_redis_client)
        
        # Mock successful ping
        mock_redis_client.ping.return_value = True
        
        health = cache_manager.health_check()
        
        assert health['status'] == 'healthy'
        assert health['redis_connected'] is True
        assert health['fallback_mode'] is False
        assert 'stats' in health
    
    def test_health_check_redis_failure(self, mock_redis_client):
        """Test health check with Redis failure."""
        cache_manager = CacheManager(redis_client=mock_redis_client)
        
        # Mock Redis ping failure
        mock_redis_client.ping.side_effect = Exception("Connection failed")
        
        health = cache_manager.health_check()
        
        assert health['status'] == 'degraded'
        assert health['redis_connected'] is False
        assert 'error' in health
    
    def test_health_check_fallback_mode(self):
        """Test health check in fallback mode."""
        cache_manager = CacheManager(redis_client=None)
        
        health = cache_manager.health_check()
        
        assert health['status'] == 'degraded'
        assert health['redis_connected'] is False
        assert health['fallback_mode'] is True
    
    def test_error_handling_redis_operations(self, mock_redis_client):
        """Test error handling in Redis operations."""
        cache_manager = CacheManager(redis_client=mock_redis_client)
        
        # Mock Redis errors
        mock_redis_client.setex.side_effect = Exception("Redis error")
        mock_redis_client.get.side_effect = Exception("Redis error")
        
        # Should not raise exceptions
        result = cache_manager.set("key", "data")
        assert result is False
        
        data = cache_manager.get("key")
        assert data is None
    
    def test_json_serialization_edge_cases(self, mock_redis_client):
        """Test JSON serialization edge cases."""
        cache_manager = CacheManager(redis_client=mock_redis_client)
        
        # Test with non-serializable data
        mock_redis_client.setex.return_value = True
        
        # Should handle serialization errors gracefully
        result = cache_manager.set("key", lambda x: x)  # Non-serializable
        assert result is False
    
    def test_local_cache_cleanup(self):
        """Test local cache cleanup in fallback mode."""
        cache_manager = CacheManager(redis_client=None, max_local_cache_size=2)
        
        # Fill cache beyond limit
        cache_manager.set("key1", "data1")
        cache_manager.set("key2", "data2")
        cache_manager.set("key3", "data3")  # Should trigger cleanup
        
        # Should have cleaned up old entries
        assert len(cache_manager.local_cache) <= 2


class TestCachedDecorator:
    """Test cases for @cached decorator."""
    
    def test_cached_decorator_with_redis(self, mock_redis_client):
        """Test @cached decorator with Redis."""
        # Mock cache manager
        mock_cache_manager = Mock()
        mock_cache_manager.get.return_value = None  # Cache miss first
        mock_cache_manager.set.return_value = True
        
        with patch('utils.cache_manager.get_cache_manager', return_value=mock_cache_manager):
            @cached(get_cache_manager(), prefix="test", ttl=60)
            def test_function(x, y):
                return x + y
            
            # First call - should execute function
            result1 = test_function(1, 2)
            assert result1 == 3
            mock_cache_manager.get.assert_called_once()
            mock_cache_manager.set.assert_called_once()
            
            # Second call - should use cache
            mock_cache_manager.get.return_value = 3  # Cache hit
            result2 = test_function(1, 2)
            assert result2 == 3
            assert mock_cache_manager.get.call_count == 2
    
    def test_cached_decorator_without_cache_manager(self):
        """Test @cached decorator when cache manager is not available."""
        with patch('utils.cache_manager.get_cache_manager', return_value=None):
            @cached(ttl=60, key_prefix="test")
            def test_function(x, y):
                return x + y
            
            # Should work without caching
            result = test_function(1, 2)
            assert result == 3
    
    def test_cached_decorator_with_different_args(self, mock_redis_client):
        """Test @cached decorator with different arguments."""
        mock_cache_manager = Mock()
        mock_cache_manager.get.return_value = None
        mock_cache_manager.set.return_value = True
        
        with patch('utils.cache_manager.get_cache_manager', return_value=mock_cache_manager):
            @cached(get_cache_manager(), prefix="test", ttl=60)
            def test_function(x, y=10):
                return x + y
            
            # Different calls should generate different cache keys
            test_function(1, 2)
            test_function(1, 3)
            test_function(2, 2)
            
            # Should have made 3 different cache calls
            assert mock_cache_manager.get.call_count == 3
            assert mock_cache_manager.set.call_count == 3
    
    def test_cached_decorator_with_complex_args(self, mock_redis_client):
        """Test @cached decorator with complex arguments."""
        mock_cache_manager = Mock()
        mock_cache_manager.get.return_value = None
        mock_cache_manager.set.return_value = True
        
        with patch('utils.cache_manager.get_cache_manager', return_value=mock_cache_manager):
            @cached(get_cache_manager(), prefix="test", ttl=60)
            def test_function(data_dict, data_list):
                return len(data_dict) + len(data_list)
            
            result = test_function({"a": 1, "b": 2}, [1, 2, 3])
            assert result == 5
            mock_cache_manager.get.assert_called_once()
    
    def test_cached_decorator_error_handling(self, mock_redis_client):
        """Test @cached decorator error handling."""
        mock_cache_manager = Mock()
        mock_cache_manager.get.side_effect = Exception("Cache error")
        
        with patch('utils.cache_manager.get_cache_manager', return_value=mock_cache_manager):
            @cached(get_cache_manager(), prefix="test", ttl=60)
            def test_function(x):
                return x * 2
            
            # Should work despite cache errors
            result = test_function(5)
            assert result == 10
    
    def test_cached_decorator_with_method(self, mock_redis_client):
        """Test @cached decorator with class methods."""
        mock_cache_manager = Mock()
        mock_cache_manager.get.return_value = None
        mock_cache_manager.set.return_value = True
        
        with patch('utils.cache_manager.get_cache_manager', return_value=mock_cache_manager):
            class TestClass:
                @cached(get_cache_manager(), prefix="method", ttl=60)
                def test_method(self, x):
                    return x * 3
            
            obj = TestClass()
            result = obj.test_method(4)
            assert result == 12
            mock_cache_manager.get.assert_called_once()


class TestGetCacheManager:
    """Test cases for get_cache_manager function."""
    
    @patch('utils.cache_manager.redis')
    def test_get_cache_manager_with_redis_config(self, mock_redis_module, mock_config):
        """Test get_cache_manager with Redis configuration."""
        # Mock Redis client creation
        mock_redis_client = Mock()
        mock_redis_module.Redis.return_value = mock_redis_client
        mock_redis_client.ping.return_value = True
        
        # Mock config
        mock_config.REDIS_HOST = 'localhost'
        mock_config.REDIS_PORT = 6379
        mock_config.REDIS_DB = 0
        
        cache_manager = get_cache_manager(mock_config)
        
        assert cache_manager is not None
        assert cache_manager.redis_client == mock_redis_client
        mock_redis_module.Redis.assert_called_once()
    
    @patch('utils.cache_manager.redis')
    def test_get_cache_manager_redis_connection_failure(self, mock_redis_module, mock_config):
        """Test get_cache_manager with Redis connection failure."""
        # Mock Redis connection failure
        mock_redis_module.Redis.side_effect = Exception("Connection failed")
        
        cache_manager = get_cache_manager(mock_config)
        
        assert cache_manager is not None
        assert cache_manager.redis_client is None
        assert cache_manager.fallback_mode is True
    
    def test_get_cache_manager_no_redis_config(self, mock_config):
        """Test get_cache_manager without Redis configuration."""
        # Remove Redis config
        if hasattr(mock_config, 'REDIS_HOST'):
            delattr(mock_config, 'REDIS_HOST')
        
        cache_manager = get_cache_manager(mock_config)
        
        assert cache_manager is not None
        assert cache_manager.redis_client is None
        assert cache_manager.fallback_mode is True
    
    def test_get_cache_manager_singleton_behavior(self, mock_config):
        """Test that get_cache_manager returns the same instance."""
        # Clear any existing instance
        if hasattr(get_cache_manager, '_instance'):
            delattr(get_cache_manager, '_instance')
        
        cache_manager1 = get_cache_manager(mock_config)
        cache_manager2 = get_cache_manager(mock_config)
        
        assert cache_manager1 is cache_manager2


@pytest.mark.integration
class TestCacheIntegration:
    """Integration tests for cache functionality."""
    
    def test_cache_with_fiinquant_adapter(self, mock_config, mock_redis_client):
        """Test cache integration with FiinQuantAdapter."""
        from utils.fiinquant_adapter import FiinQuantAdapter
        
        # Mock cache manager
        mock_cache_manager = Mock()
        mock_cache_manager.get.return_value = None
        mock_cache_manager.set.return_value = True
        
        with patch('utils.cache_manager.get_cache_manager', return_value=mock_cache_manager):
            adapter = FiinQuantAdapter(mock_config)
            
            # Should have cache manager available
            assert hasattr(adapter, 'cache_manager')
            assert adapter.cache_manager == mock_cache_manager
    
    def test_cache_with_strategy(self, mock_config, mock_redis_client):
        """Test cache integration with strategy."""
        from strategy.rsi_psar_engulfing import RSIPSAREngulfingStrategy
        
        # Mock cache manager
        mock_cache_manager = Mock()
        
        with patch('utils.cache_manager.get_cache_manager', return_value=mock_cache_manager):
            with patch('strategy.rsi_psar_engulfing.CACHE_AVAILABLE', True):
                strategy = RSIPSAREngulfingStrategy(mock_config)
                
                # Strategy methods should be decorated with @cached
                assert hasattr(strategy.analyze_ticker, '__wrapped__')
    
    @pytest.mark.redis
    def test_real_redis_integration(self, mock_config):
        """Test with real Redis (requires Redis server)."""
        # This test requires a real Redis server
        # Skip if Redis is not available
        try:
            import redis
            client = redis.Redis(host='localhost', port=6379, db=15)  # Use test DB
            client.ping()
        except:
            pytest.skip("Redis server not available")
        
        cache_manager = CacheManager(redis_client=client)
        
        # Test basic operations
        cache_manager.set("test_key", {"data": "test"}, ttl=10)
        result = cache_manager.get("test_key")
        
        assert result == {"data": "test"}
        
        # Cleanup
        cache_manager.delete("test_key")
    
    def test_cache_performance_benchmark(self, mock_redis_client):
        """Test cache performance characteristics."""
        cache_manager = CacheManager(redis_client=None)  # Use fallback mode
        
        # Benchmark set operations
        start_time = time.time()
        for i in range(1000):
            cache_manager.set(f"key_{i}", f"data_{i}")
        set_time = time.time() - start_time
        
        # Benchmark get operations
        start_time = time.time()
        for i in range(1000):
            cache_manager.get(f"key_{i}")
        get_time = time.time() - start_time
        
        # Should be reasonably fast
        assert set_time < 1.0  # Less than 1 second for 1000 sets
        assert get_time < 1.0  # Less than 1 second for 1000 gets
        
        # Check hit rate
        stats = cache_manager.get_stats()
        assert stats['hit_rate'] == 1.0  # All should be hits
    
    def test_cache_memory_usage(self, mock_redis_client):
        """Test cache memory usage in fallback mode."""
        cache_manager = CacheManager(redis_client=None, max_local_cache_size=100)
        
        # Fill cache beyond limit
        for i in range(200):
            cache_manager.set(f"key_{i}", f"data_{i}")
        
        # Should not exceed memory limit
        assert len(cache_manager.local_cache) <= 100
    
    def test_concurrent_cache_access(self, mock_redis_client):
        """Test concurrent cache access."""
        import threading
        
        cache_manager = CacheManager(redis_client=None)
        results = []
        
        def cache_worker(worker_id):
            for i in range(10):
                key = f"worker_{worker_id}_key_{i}"
                cache_manager.set(key, f"data_{i}")
                result = cache_manager.get(key)
                results.append(result)
        
        # Create multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=cache_worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        # Should have all results
        assert len(results) == 50
        assert all(result is not None for result in results)