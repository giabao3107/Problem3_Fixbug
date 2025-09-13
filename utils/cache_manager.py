"""Advanced Caching Manager for Realtime Alert System
Provides Redis and in-memory caching for performance optimization.
"""

import json
import pickle
import hashlib
import logging
from typing import Any, Dict, List, Optional, Union, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from functools import wraps
import threading
from pathlib import Path

# Redis support (optional)
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


@dataclass
class CacheEntry:
    """Cache entry with metadata."""
    key: str
    value: Any
    created_at: datetime
    expires_at: Optional[datetime]
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    size_bytes: int = 0


class CacheManager:
    """
    Advanced caching manager with multiple backends and strategies.
    """
    
    def __init__(self, 
                 redis_host: str = 'localhost',
                 redis_port: int = 6379,
                 redis_db: int = 0,
                 redis_password: Optional[str] = None,
                 use_redis: bool = True,
                 memory_cache_size: int = 1000,
                 default_ttl: int = 300):
        """
        Initialize cache manager.
        
        Args:
            redis_host: Redis server host
            redis_port: Redis server port
            redis_db: Redis database number
            redis_password: Redis password
            use_redis: Whether to use Redis (falls back to memory if unavailable)
            memory_cache_size: Maximum number of items in memory cache
            default_ttl: Default time-to-live in seconds
        """
        self.logger = logging.getLogger(__name__)
        self.default_ttl = default_ttl
        self.memory_cache_size = memory_cache_size
        
        # Memory cache
        self._memory_cache: Dict[str, CacheEntry] = {}
        self._cache_lock = threading.RLock()
        
        # Redis cache
        self.redis_client = None
        self.use_redis = use_redis and REDIS_AVAILABLE
        
        if self.use_redis:
            try:
                self.redis_client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    db=redis_db,
                    password=redis_password,
                    decode_responses=False,  # We'll handle encoding
                    socket_connect_timeout=5,
                    socket_timeout=5
                )
                # Test connection
                self.redis_client.ping()
                self.logger.info("Redis cache initialized successfully")
            except Exception as e:
                self.logger.warning(f"Redis unavailable, falling back to memory cache: {e}")
                self.redis_client = None
                self.use_redis = False
        else:
            self.logger.info("Using memory-only cache")
    
    def _generate_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate cache key from prefix and arguments."""
        # Create deterministic key from arguments
        key_data = {
            'args': args,
            'kwargs': sorted(kwargs.items())
        }
        key_hash = hashlib.md5(json.dumps(key_data, sort_keys=True, default=str).encode()).hexdigest()
        return f"{prefix}:{key_hash}"
    
    def _serialize_value(self, value: Any) -> bytes:
        """Serialize value for storage."""
        try:
            # Try JSON first for simple types
            if isinstance(value, (str, int, float, bool, list, dict)):
                return json.dumps(value).encode('utf-8')
            else:
                # Use pickle for complex objects
                return pickle.dumps(value)
        except Exception as e:
            self.logger.error(f"Failed to serialize value: {e}")
            raise
    
    def _deserialize_value(self, data: bytes) -> Any:
        """Deserialize value from storage."""
        try:
            # Try JSON first
            try:
                return json.loads(data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                # Fall back to pickle
                return pickle.loads(data)
        except Exception as e:
            self.logger.error(f"Failed to deserialize value: {e}")
            raise
    
    def _cleanup_memory_cache(self):
        """Clean up expired entries and enforce size limits."""
        with self._cache_lock:
            now = datetime.now()
            
            # Remove expired entries
            expired_keys = [
                key for key, entry in self._memory_cache.items()
                if entry.expires_at and entry.expires_at < now
            ]
            
            for key in expired_keys:
                del self._memory_cache[key]
            
            # Enforce size limit (LRU eviction)
            if len(self._memory_cache) > self.memory_cache_size:
                # Sort by last accessed time (oldest first)
                sorted_entries = sorted(
                    self._memory_cache.items(),
                    key=lambda x: x[1].last_accessed or x[1].created_at
                )
                
                # Remove oldest entries
                excess_count = len(self._memory_cache) - self.memory_cache_size
                for key, _ in sorted_entries[:excess_count]:
                    del self._memory_cache[key]
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set cache value.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (None for default)
            
        Returns:
            bool: Success status
        """
        if ttl is None:
            ttl = self.default_ttl
        
        try:
            serialized_value = self._serialize_value(value)
            expires_at = datetime.now() + timedelta(seconds=ttl) if ttl > 0 else None
            
            # Store in Redis if available
            if self.use_redis and self.redis_client:
                try:
                    if ttl > 0:
                        self.redis_client.setex(key, ttl, serialized_value)
                    else:
                        self.redis_client.set(key, serialized_value)
                except Exception as e:
                    self.logger.warning(f"Redis set failed, using memory cache: {e}")
            
            # Store in memory cache
            with self._cache_lock:
                self._memory_cache[key] = CacheEntry(
                    key=key,
                    value=value,
                    created_at=datetime.now(),
                    expires_at=expires_at,
                    size_bytes=len(serialized_value)
                )
                
                # Cleanup if needed
                if len(self._memory_cache) % 100 == 0:  # Periodic cleanup
                    self._cleanup_memory_cache()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to set cache key {key}: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get cache value.
        
        Args:
            key: Cache key
            default: Default value if not found
            
        Returns:
            Cached value or default
        """
        try:
            # Try memory cache first
            with self._cache_lock:
                if key in self._memory_cache:
                    entry = self._memory_cache[key]
                    
                    # Check expiration
                    if entry.expires_at and entry.expires_at < datetime.now():
                        del self._memory_cache[key]
                    else:
                        # Update access info
                        entry.access_count += 1
                        entry.last_accessed = datetime.now()
                        return entry.value
            
            # Try Redis if available
            if self.use_redis and self.redis_client:
                try:
                    data = self.redis_client.get(key)
                    if data is not None:
                        value = self._deserialize_value(data)
                        
                        # Store in memory cache for faster access
                        with self._cache_lock:
                            self._memory_cache[key] = CacheEntry(
                                key=key,
                                value=value,
                                created_at=datetime.now(),
                                expires_at=None,  # Redis handles expiration
                                access_count=1,
                                last_accessed=datetime.now()
                            )
                        
                        return value
                except Exception as e:
                    self.logger.warning(f"Redis get failed: {e}")
            
            return default
            
        except Exception as e:
            self.logger.error(f"Failed to get cache key {key}: {e}")
            return default
    
    def delete(self, key: str) -> bool:
        """
        Delete cache entry.
        
        Args:
            key: Cache key
            
        Returns:
            bool: Success status
        """
        try:
            # Delete from memory cache
            with self._cache_lock:
                if key in self._memory_cache:
                    del self._memory_cache[key]
            
            # Delete from Redis
            if self.use_redis and self.redis_client:
                try:
                    self.redis_client.delete(key)
                except Exception as e:
                    self.logger.warning(f"Redis delete failed: {e}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to delete cache key {key}: {e}")
            return False
    
    def clear(self, pattern: Optional[str] = None) -> bool:
        """
        Clear cache entries.
        
        Args:
            pattern: Key pattern to match (None for all)
            
        Returns:
            bool: Success status
        """
        try:
            if pattern:
                # Clear matching keys
                keys_to_delete = []
                
                # Memory cache
                with self._cache_lock:
                    for key in self._memory_cache:
                        if pattern in key:
                            keys_to_delete.append(key)
                    
                    for key in keys_to_delete:
                        del self._memory_cache[key]
                
                # Redis cache
                if self.use_redis and self.redis_client:
                    try:
                        redis_keys = self.redis_client.keys(f"*{pattern}*")
                        if redis_keys:
                            self.redis_client.delete(*redis_keys)
                    except Exception as e:
                        self.logger.warning(f"Redis pattern delete failed: {e}")
            else:
                # Clear all
                with self._cache_lock:
                    self._memory_cache.clear()
                
                if self.use_redis and self.redis_client:
                    try:
                        self.redis_client.flushdb()
                    except Exception as e:
                        self.logger.warning(f"Redis flush failed: {e}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to clear cache: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._cache_lock:
            memory_stats = {
                'entries': len(self._memory_cache),
                'total_size_bytes': sum(entry.size_bytes for entry in self._memory_cache.values()),
                'total_access_count': sum(entry.access_count for entry in self._memory_cache.values())
            }
        
        redis_stats = {}
        if self.use_redis and self.redis_client:
            try:
                info = self.redis_client.info('memory')
                redis_stats = {
                    'used_memory': info.get('used_memory', 0),
                    'used_memory_human': info.get('used_memory_human', '0B')
                }
            except Exception as e:
                self.logger.warning(f"Failed to get Redis stats: {e}")
        
        return {
            'memory_cache': memory_stats,
            'redis_cache': redis_stats,
            'redis_available': self.use_redis
        }


def cached(cache_manager: CacheManager, 
          prefix: str = 'func',
          ttl: Optional[int] = None,
          key_func: Optional[Callable] = None):
    """
    Decorator for caching function results.
    
    Args:
        cache_manager: CacheManager instance
        prefix: Cache key prefix
        ttl: Time-to-live in seconds
        key_func: Custom key generation function
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = cache_manager._generate_key(f"{prefix}_{func.__name__}", *args, **kwargs)
            
            # Try to get from cache
            result = cache_manager.get(cache_key)
            if result is not None:
                return result
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            cache_manager.set(cache_key, result, ttl)
            
            return result
        
        # Add cache management methods
        wrapper.cache_clear = lambda: cache_manager.clear(f"{prefix}_{func.__name__}")
        wrapper.cache_info = lambda: cache_manager.get_stats()
        
        return wrapper
    return decorator


# Global cache manager instance
_global_cache_manager = None


def get_cache_manager() -> CacheManager:
    """Get global cache manager instance."""
    global _global_cache_manager
    if _global_cache_manager is None:
        _global_cache_manager = CacheManager()
    return _global_cache_manager


def init_cache_manager(config: Dict[str, Any]) -> CacheManager:
    """
    Initialize global cache manager with configuration.
    
    Args:
        config: Cache configuration
        
    Returns:
        CacheManager: Initialized cache manager
    """
    global _global_cache_manager
    
    cache_config = config.get('cache', {})
    
    _global_cache_manager = CacheManager(
        redis_host=cache_config.get('redis_host', 'localhost'),
        redis_port=cache_config.get('redis_port', 6379),
        redis_db=cache_config.get('redis_db', 0),
        redis_password=cache_config.get('redis_password'),
        use_redis=cache_config.get('use_redis', True),
        memory_cache_size=cache_config.get('memory_cache_size', 1000),
        default_ttl=cache_config.get('default_ttl', 300)
    )
    
    return _global_cache_manager