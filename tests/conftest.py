import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
import tempfile
import os
from typing import Dict, Any

# Test data fixtures
@pytest.fixture
def sample_ohlcv_data():
    """Generate sample OHLCV data for testing."""
    dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
    np.random.seed(42)  # For reproducible tests
    
    # Generate realistic price data
    base_price = 100
    price_changes = np.random.normal(0, 0.02, 100)  # 2% daily volatility
    prices = [base_price]
    
    for change in price_changes[1:]:
        new_price = prices[-1] * (1 + change)
        prices.append(max(new_price, 1))  # Ensure positive prices
    
    data = []
    for i, date in enumerate(dates):
        close = prices[i]
        high = close * (1 + abs(np.random.normal(0, 0.01)))
        low = close * (1 - abs(np.random.normal(0, 0.01)))
        open_price = low + (high - low) * np.random.random()
        volume = int(np.random.normal(1000000, 200000))
        
        data.append({
            'timestamp': date,
            'open': round(open_price, 2),
            'high': round(high, 2),
            'low': round(low, 2),
            'close': round(close, 2),
            'volume': max(volume, 100000)
        })
    
    return pd.DataFrame(data)

@pytest.fixture
def sample_market_data():
    """Generate sample market data for multiple tickers."""
    tickers = ['VIC', 'VHM', 'VCB', 'BID', 'CTG']
    market_data = {}
    
    for ticker in tickers:
        dates = pd.date_range(start='2024-01-01', periods=50, freq='D')
        np.random.seed(hash(ticker) % 1000)  # Different seed per ticker
        
        base_price = np.random.uniform(50, 200)
        price_changes = np.random.normal(0, 0.015, 50)
        prices = [base_price]
        
        for change in price_changes[1:]:
            new_price = prices[-1] * (1 + change)
            prices.append(max(new_price, 1))
        
        data = []
        for i, date in enumerate(dates):
            close = prices[i]
            high = close * (1 + abs(np.random.normal(0, 0.008)))
            low = close * (1 - abs(np.random.normal(0, 0.008)))
            open_price = low + (high - low) * np.random.random()
            volume = int(np.random.normal(800000, 150000))
            
            data.append({
                'timestamp': date,
                'open': round(open_price, 2),
                'high': round(high, 2),
                'low': round(low, 2),
                'close': round(close, 2),
                'volume': max(volume, 50000),
                'ticker': ticker
            })
        
        market_data[ticker] = pd.DataFrame(data)
    
    return market_data

@pytest.fixture
def mock_config():
    """Mock configuration for testing."""
    return {
        'fiinquant': {
            'username': 'test_user',
            'password': 'test_pass',
            'retry_attempts': 3,
            'retry_delay': 1
        },
        'strategy': {
            'rsi': {
                'period': 14,
                'oversold': 30,
                'overbought': 70
            },
            'psar': {
                'af_init': 0.02,
                'af_step': 0.02,
                'af_max': 0.20
            },
            'engulfing': {
                'min_body_ratio': 0.5
            },
            'volume': {
                'avg_period': 20,
                'anomaly_threshold': 1.5
            }
        },
        'risk_management': {
            'max_position_size': 0.1,
            'stop_loss_pct': 0.05,
            'take_profit_pct': 0.10,
            'max_daily_loss': 0.02
        },
        'email': {
            'smtp_server': 'smtp.gmail.com',
            'smtp_port': 587,
            'sender_email': 'test@example.com',
            'sender_password': 'test_password',
            'recipient_emails': ['recipient@example.com']
        },
        'telegram': {
            'bot_token': 'test_bot_token',
            'chat_ids': ['123456789']
        },
        'cache': {
            'redis': {
                'host': 'localhost',
                'port': 6379,
                'db': 1,
                'password': None
            },
            'memory': {
                'max_size': 1000
            },
            'strategies': {
                'market_data': {'ttl': 300, 'type': 'redis'},
                'indicators': {'ttl': 600, 'type': 'memory'},
                'strategy_results': {'ttl': 300, 'type': 'redis'}
            }
        },
        'monitoring': {
            'log_level': 'INFO',
            'performance_threshold': 5.0,
            'cache_hit_ratio_threshold': 0.8
        }
    }

@pytest.fixture
def mock_fiinquant_client():
    """Mock FiinQuant client for testing."""
    client = Mock()
    client.login.return_value = True
    client.is_logged_in.return_value = True
    client.get_historical_data.return_value = pd.DataFrame({
        'open': [100, 101, 102],
        'high': [105, 106, 107],
        'low': [95, 96, 97],
        'close': [103, 104, 105],
        'volume': [1000000, 1100000, 1200000]
    })
    return client

@pytest.fixture
def mock_email_service():
    """Mock email service for testing."""
    service = Mock()
    service.send_buy_alert.return_value = True
    service.send_sell_alert.return_value = True
    service.send_risk_alert.return_value = True
    service.send_daily_summary.return_value = True
    service.send_portfolio_update.return_value = True
    service.is_healthy.return_value = True
    return service

@pytest.fixture
def mock_telegram_bot():
    """Mock Telegram bot for testing."""
    bot = Mock()
    bot.send_buy_signal.return_value = True
    bot.send_sell_signal.return_value = True
    bot.send_risk_alert.return_value = True
    bot.send_daily_summary.return_value = True
    bot.send_portfolio_update.return_value = True
    bot.send_automated_strategy_alert.return_value = True
    return bot

@pytest.fixture
def mock_cache_manager():
    """Mock cache manager for testing."""
    cache = Mock()
    cache.get.return_value = None
    cache.set.return_value = True
    cache.delete.return_value = True
    cache.clear.return_value = True
    cache.get_stats.return_value = {
        'hits': 100,
        'misses': 20,
        'hit_ratio': 0.83,
        'total_keys': 50
    }
    return cache

@pytest.fixture
def temp_config_file(mock_config):
    """Create a temporary config file for testing."""
    import yaml
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(mock_config, f)
        temp_file = f.name
    
    yield temp_file
    
    # Cleanup
    if os.path.exists(temp_file):
        os.unlink(temp_file)

@pytest.fixture(autouse=True)
def setup_test_environment():
    """Setup test environment before each test."""
    # Set test environment variables
    os.environ['TESTING'] = 'true'
    os.environ['LOG_LEVEL'] = 'DEBUG'
    
    yield
    
    # Cleanup after test
    if 'TESTING' in os.environ:
        del os.environ['TESTING']
    if 'LOG_LEVEL' in os.environ:
        del os.environ['LOG_LEVEL']

@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    redis_mock = Mock()
    redis_mock.get.return_value = None
    redis_mock.set.return_value = True
    redis_mock.delete.return_value = 1
    redis_mock.flushdb.return_value = True
    redis_mock.ping.return_value = True
    redis_mock.keys.return_value = []
    return redis_mock

# Test utilities
class TestDataGenerator:
    """Utility class for generating test data."""
    
    @staticmethod
    def create_trading_signal(ticker='VIC', signal_type='buy', confidence=0.8):
        """Create a sample trading signal."""
        from strategy.rsi_psar_engulfing import TradingSignal
        
        return TradingSignal(
            ticker=ticker,
            timestamp=datetime.now(),
            signal_type=signal_type,
            confidence=confidence,
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=110.0,
            reason=f"Test {signal_type} signal",
            metadata={'test': True}
        )
    
    @staticmethod
    def create_market_data_point(ticker='VIC', price=100.0):
        """Create a sample market data point."""
        from utils.fiinquant_adapter import MarketDataPoint
        
        return MarketDataPoint(
            ticker=ticker,
            timestamp=datetime.now(),
            open=price * 0.99,
            high=price * 1.02,
            low=price * 0.97,
            close=price,
            volume=1000000,
            change=price * 0.01,
            change_percent=1.0
        )

# Make test utilities available
@pytest.fixture
def test_data_generator():
    """Provide test data generator."""
    return TestDataGenerator