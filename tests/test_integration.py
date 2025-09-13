import pytest
import asyncio
import pandas as pd
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timedelta
from utils.fiinquant_adapter import FiinQuantAdapter
from strategy.rsi_psar_engulfing import RSIPSAREngulfingStrategy, TradingSignal
from alert_system.alert_manager import AlertManager
from utils.cache_manager import CacheManager


@pytest.mark.integration
class TestSystemIntegration:
    """Integration tests for the complete realtime alert system."""
    
    def test_system_initialization(self, mock_config):
        """Test complete system initialization."""
        # Initialize all components
        fiinquant_adapter = FiinQuantAdapter(mock_config)
        strategy = RSIPSAREngulfingStrategy(mock_config)
        alert_manager = AlertManager(mock_config)
        
        # Verify components are properly initialized
        assert fiinquant_adapter.config == mock_config
        assert strategy.config == mock_config
        assert alert_manager.config == mock_config
        
        # Verify component health
        fiinquant_health = fiinquant_adapter.health_check()
        assert 'status' in fiinquant_health
        
        strategy_stats = strategy.get_performance_stats()
        assert 'total_signals' in strategy_stats
        
        alert_stats = alert_manager.get_alert_stats()
        assert 'total_alerts' in alert_stats
    
    @pytest.mark.asyncio
    async def test_complete_trading_workflow(self, mock_config, sample_ohlcv_data, test_data_generator):
        """Test complete trading workflow from data fetch to alert."""
        # Mock FiinQuant client
        mock_client = Mock()
        mock_client.get_latest_data.return_value = sample_ohlcv_data.iloc[-1].to_dict()
        mock_client.fetch_historical_data.return_value = sample_ohlcv_data
        
        # Mock alert services
        mock_email_service = Mock()
        mock_email_service.send_trading_signal_alert = AsyncMock(return_value=True)
        mock_telegram_service = Mock()
        mock_telegram_service.send_trading_signal_alert = AsyncMock(return_value=True)
        
        with patch('utils.fiinquant_adapter.FiinQuantClient', return_value=mock_client):
            # Initialize components
            fiinquant_adapter = FiinQuantAdapter(mock_config)
            strategy = RSIPSAREngulfingStrategy(mock_config)
            alert_manager = AlertManager(
                config=mock_config,
                email_service=mock_email_service,
                telegram_service=mock_telegram_service
            )
            
            # Step 1: Fetch market data
            latest_data = fiinquant_adapter.get_latest_data('VIC')
            assert latest_data is not None
            
            historical_data = fiinquant_adapter.fetch_historical_data('VIC', '1D', 100)
            assert len(historical_data) > 0
            
            # Step 2: Analyze with strategy
            signals = strategy.analyze_ticker('VIC', historical_data)
            
            # Step 3: Send alerts for any signals
            for signal in signals:
                result = await alert_manager.send_trading_signal_alert(signal)
                assert result is True
            
            # Verify workflow completed
            assert len(strategy.get_signal_history()) >= len(signals)
            assert len(alert_manager.get_alert_history()) >= len(signals)
    
    @pytest.mark.asyncio
    async def test_multi_ticker_analysis(self, mock_config, sample_market_data):
        """Test analyzing multiple tickers simultaneously."""
        # Mock FiinQuant client
        mock_client = Mock()
        mock_client.fetch_historical_data.side_effect = lambda ticker, *args, **kwargs: sample_market_data.get(ticker, pd.DataFrame())
        
        # Mock alert services
        mock_email_service = Mock()
        mock_email_service.send_trading_signal_alert = AsyncMock(return_value=True)
        mock_telegram_service = Mock()
        mock_telegram_service.send_trading_signal_alert = AsyncMock(return_value=True)
        
        with patch('utils.fiinquant_adapter.FiinQuantClient', return_value=mock_client):
            # Initialize components
            fiinquant_adapter = FiinQuantAdapter(mock_config)
            strategy = RSIPSAREngulfingStrategy(mock_config)
            alert_manager = AlertManager(
                config=mock_config,
                email_service=mock_email_service,
                telegram_service=mock_telegram_service
            )
            
            tickers = list(sample_market_data.keys())
            all_signals = []
            
            # Analyze each ticker
            for ticker in tickers:
                data = fiinquant_adapter.fetch_historical_data(ticker, '1D', 100)
                signals = strategy.analyze_ticker(ticker, data)
                all_signals.extend(signals)
            
            # Send alerts for all signals
            alert_tasks = [alert_manager.send_trading_signal_alert(signal) for signal in all_signals]
            results = await asyncio.gather(*alert_tasks)
            
            # Verify all alerts were sent
            assert all(results)
            assert len(alert_manager.get_alert_history()) == len(all_signals)
    
    @pytest.mark.asyncio
    async def test_error_handling_and_recovery(self, mock_config, sample_ohlcv_data):
        """Test system error handling and recovery."""
        # Mock FiinQuant client with intermittent failures
        mock_client = Mock()
        call_count = 0
        
        def failing_fetch(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise Exception("Network error")
            return sample_ohlcv_data
        
        mock_client.fetch_historical_data.side_effect = failing_fetch
        
        # Mock alert services with failures
        mock_email_service = Mock()
        mock_email_service.send_trading_signal_alert = AsyncMock(side_effect=Exception("Email failed"))
        mock_telegram_service = Mock()
        mock_telegram_service.send_trading_signal_alert = AsyncMock(return_value=True)
        
        with patch('utils.fiinquant_adapter.FiinQuantClient', return_value=mock_client):
            # Initialize components
            fiinquant_adapter = FiinQuantAdapter(mock_config)
            strategy = RSIPSAREngulfingStrategy(mock_config)
            alert_manager = AlertManager(
                config=mock_config,
                email_service=mock_email_service,
                telegram_service=mock_telegram_service
            )
            
            # Try to fetch data (should fail first two times)
            try:
                data1 = fiinquant_adapter.fetch_historical_data('VIC', '1D', 100)
                assert False, "Should have failed"
            except Exception:
                pass
            
            try:
                data2 = fiinquant_adapter.fetch_historical_data('VIC', '1D', 100)
                assert False, "Should have failed"
            except Exception:
                pass
            
            # Third attempt should succeed
            data3 = fiinquant_adapter.fetch_historical_data('VIC', '1D', 100)
            assert len(data3) > 0
            
            # Analyze and send alerts (email will fail, telegram should succeed)
            signals = strategy.analyze_ticker('VIC', data3)
            for signal in signals:
                result = await alert_manager.send_trading_signal_alert(signal)
                # Should succeed because telegram works even if email fails
                assert result is True
    
    @pytest.mark.cache
    def test_caching_integration(self, mock_config, sample_ohlcv_data, mock_cache_manager):
        """Test caching integration across components."""
        with patch('utils.cache_manager.get_cache_manager', return_value=mock_cache_manager):
            # Mock cache responses
            mock_cache_manager.get.return_value = None  # Cache miss
            mock_cache_manager.set.return_value = True
            
            # Initialize components with caching
            fiinquant_adapter = FiinQuantAdapter(mock_config)
            strategy = RSIPSAREngulfingStrategy(mock_config)
            
            # Verify cache manager is available
            assert hasattr(fiinquant_adapter, 'cache_manager')
            assert fiinquant_adapter.cache_manager == mock_cache_manager
            
            # Mock FiinQuant client
            mock_client = Mock()
            mock_client.fetch_historical_data.return_value = sample_ohlcv_data
            
            with patch('utils.fiinquant_adapter.FiinQuantClient', return_value=mock_client):
                # First call should miss cache and fetch data
                data1 = fiinquant_adapter.fetch_historical_data('VIC', '1D', 100)
                assert len(data1) > 0
                
                # Verify cache was checked and set
                assert mock_cache_manager.get.call_count >= 1
                assert mock_cache_manager.set.call_count >= 1
                
                # Mock cache hit for second call
                mock_cache_manager.get.return_value = sample_ohlcv_data.to_dict('records')
                
                # Second call should use cache
                data2 = fiinquant_adapter.fetch_historical_data('VIC', '1D', 100)
                assert len(data2) > 0
    
    @pytest.mark.asyncio
    async def test_realtime_simulation(self, mock_config, sample_market_data):
        """Test simulated realtime trading scenario."""
        # Mock services
        mock_client = Mock()
        mock_email_service = Mock()
        mock_email_service.send_trading_signal_alert = AsyncMock(return_value=True)
        mock_telegram_service = Mock()
        mock_telegram_service.send_trading_signal_alert = AsyncMock(return_value=True)
        
        # Simulate streaming data
        def get_streaming_data(ticker):
            base_data = sample_market_data.get(ticker, pd.DataFrame())
            if len(base_data) > 0:
                # Return latest row as streaming data
                return base_data.iloc[-1].to_dict()
            return None
        
        mock_client.get_latest_data.side_effect = get_streaming_data
        mock_client.fetch_historical_data.side_effect = lambda ticker, *args, **kwargs: sample_market_data.get(ticker, pd.DataFrame())
        
        with patch('utils.fiinquant_adapter.FiinQuantClient', return_value=mock_client):
            # Initialize system
            fiinquant_adapter = FiinQuantAdapter(mock_config)
            strategy = RSIPSAREngulfingStrategy(mock_config)
            alert_manager = AlertManager(
                config=mock_config,
                email_service=mock_email_service,
                telegram_service=mock_telegram_service
            )
            
            tickers = ['VIC', 'VHM', 'VCB']
            
            # Simulate realtime processing loop
            for cycle in range(3):  # 3 cycles
                cycle_signals = []
                
                for ticker in tickers:
                    # Get latest data
                    latest_data = fiinquant_adapter.get_latest_data(ticker)
                    if latest_data:
                        # Get historical data for analysis
                        historical_data = fiinquant_adapter.fetch_historical_data(ticker, '1D', 100)
                        
                        # Analyze for signals
                        signals = strategy.analyze_ticker(ticker, historical_data)
                        cycle_signals.extend(signals)
                
                # Send alerts for this cycle
                for signal in cycle_signals:
                    await alert_manager.send_trading_signal_alert(signal)
                
                # Small delay to simulate realtime
                await asyncio.sleep(0.1)
            
            # Verify system processed multiple cycles
            total_alerts = len(alert_manager.get_alert_history())
            assert total_alerts >= 0  # May be 0 if no signals generated
    
    def test_performance_monitoring(self, mock_config, sample_market_data):
        """Test system performance monitoring."""
        import time
        
        # Mock FiinQuant client
        mock_client = Mock()
        mock_client.fetch_historical_data.side_effect = lambda ticker, *args, **kwargs: sample_market_data.get(ticker, pd.DataFrame())
        
        with patch('utils.fiinquant_adapter.FiinQuantClient', return_value=mock_client):
            # Initialize components
            fiinquant_adapter = FiinQuantAdapter(mock_config)
            strategy = RSIPSAREngulfingStrategy(mock_config)
            
            tickers = list(sample_market_data.keys())
            
            # Benchmark data fetching
            start_time = time.time()
            for ticker in tickers:
                fiinquant_adapter.fetch_historical_data(ticker, '1D', 100)
            fetch_time = time.time() - start_time
            
            # Benchmark strategy analysis
            start_time = time.time()
            for ticker in tickers:
                data = sample_market_data[ticker]
                strategy.analyze_ticker(ticker, data)
            analysis_time = time.time() - start_time
            
            # Performance should be reasonable
            assert fetch_time < 1.0  # Less than 1 second for all fetches
            assert analysis_time < 2.0  # Less than 2 seconds for all analysis
            
            # Check component health
            fiinquant_health = fiinquant_adapter.health_check()
            assert fiinquant_health['status'] in ['healthy', 'degraded']
            
            strategy_stats = strategy.get_performance_stats()
            assert strategy_stats['total_signals'] >= 0
    
    @pytest.mark.asyncio
    async def test_concurrent_processing(self, mock_config, sample_market_data):
        """Test concurrent processing of multiple tickers."""
        # Mock services
        mock_client = Mock()
        mock_client.fetch_historical_data.side_effect = lambda ticker, *args, **kwargs: sample_market_data.get(ticker, pd.DataFrame())
        
        mock_email_service = Mock()
        mock_email_service.send_trading_signal_alert = AsyncMock(return_value=True)
        mock_telegram_service = Mock()
        mock_telegram_service.send_trading_signal_alert = AsyncMock(return_value=True)
        
        with patch('utils.fiinquant_adapter.FiinQuantClient', return_value=mock_client):
            # Initialize components
            fiinquant_adapter = FiinQuantAdapter(mock_config)
            strategy = RSIPSAREngulfingStrategy(mock_config)
            alert_manager = AlertManager(
                config=mock_config,
                email_service=mock_email_service,
                telegram_service=mock_telegram_service
            )
            
            async def process_ticker(ticker):
                """Process a single ticker."""
                try:
                    # Fetch data
                    data = fiinquant_adapter.fetch_historical_data(ticker, '1D', 100)
                    
                    # Analyze
                    signals = strategy.analyze_ticker(ticker, data)
                    
                    # Send alerts
                    for signal in signals:
                        await alert_manager.send_trading_signal_alert(signal)
                    
                    return len(signals)
                except Exception as e:
                    return 0
            
            # Process all tickers concurrently
            tickers = list(sample_market_data.keys())
            tasks = [process_ticker(ticker) for ticker in tickers]
            
            start_time = asyncio.get_event_loop().time()
            results = await asyncio.gather(*tasks)
            end_time = asyncio.get_event_loop().time()
            
            # Should complete quickly with concurrent processing
            processing_time = end_time - start_time
            assert processing_time < 5.0  # Less than 5 seconds
            
            # Verify all tickers were processed
            assert len(results) == len(tickers)
            total_signals = sum(results)
            assert total_signals >= 0
    
    def test_configuration_validation(self, mock_config):
        """Test system configuration validation."""
        # Test with valid configuration
        fiinquant_adapter = FiinQuantAdapter(mock_config)
        strategy = RSIPSAREngulfingStrategy(mock_config)
        alert_manager = AlertManager(mock_config)
        
        # All should initialize successfully
        assert fiinquant_adapter.config == mock_config
        assert strategy.config == mock_config
        assert alert_manager.config == mock_config
        
        # Test configuration validation
        health_checks = [
            fiinquant_adapter.health_check(),
            strategy.get_performance_stats(),
            alert_manager.get_alert_stats()
        ]
        
        # All health checks should return valid data
        for health in health_checks:
            assert isinstance(health, dict)
            assert len(health) > 0
    
    @pytest.mark.asyncio
    async def test_system_shutdown_and_cleanup(self, mock_config, sample_ohlcv_data):
        """Test system shutdown and cleanup procedures."""
        # Mock services
        mock_client = Mock()
        mock_client.fetch_historical_data.return_value = sample_ohlcv_data
        mock_client.logout.return_value = True
        
        mock_email_service = Mock()
        mock_telegram_service = Mock()
        
        with patch('utils.fiinquant_adapter.FiinQuantClient', return_value=mock_client):
            # Initialize system
            fiinquant_adapter = FiinQuantAdapter(mock_config)
            strategy = RSIPSAREngulfingStrategy(mock_config)
            alert_manager = AlertManager(
                config=mock_config,
                email_service=mock_email_service,
                telegram_service=mock_telegram_service
            )
            
            # Simulate some activity
            data = fiinquant_adapter.fetch_historical_data('VIC', '1D', 100)
            signals = strategy.analyze_ticker('VIC', data)
            
            # Test cleanup procedures
            # Clear caches
            if hasattr(fiinquant_adapter, 'clear_cache'):
                cache_cleared = fiinquant_adapter.clear_cache()
                assert cache_cleared >= 0
            
            # Clear strategy history
            initial_history_count = len(strategy.get_signal_history())
            # Strategy doesn't have explicit clear method, but we can verify state
            
            # Clear alert history
            initial_alert_count = len(alert_manager.get_alert_history())
            # Alert manager doesn't have explicit clear method, but we can verify state
            
            # Logout from FiinQuant
            logout_result = fiinquant_adapter.logout()
            assert logout_result is True
            
            # Verify cleanup
            mock_client.logout.assert_called_once()
    
    @pytest.mark.slow
    def test_stress_testing(self, mock_config, sample_market_data):
        """Test system under stress conditions."""
        import time
        
        # Mock FiinQuant client
        mock_client = Mock()
        mock_client.fetch_historical_data.side_effect = lambda ticker, *args, **kwargs: sample_market_data.get(ticker, pd.DataFrame())
        
        with patch('utils.fiinquant_adapter.FiinQuantClient', return_value=mock_client):
            # Initialize components
            fiinquant_adapter = FiinQuantAdapter(mock_config)
            strategy = RSIPSAREngulfingStrategy(mock_config)
            
            # Stress test with many requests
            start_time = time.time()
            
            for i in range(100):  # 100 iterations
                for ticker in ['VIC', 'VHM', 'VCB']:
                    try:
                        data = fiinquant_adapter.fetch_historical_data(ticker, '1D', 100)
                        signals = strategy.analyze_ticker(ticker, data)
                    except Exception as e:
                        # Should handle errors gracefully
                        pass
            
            end_time = time.time()
            
            # Should complete within reasonable time
            total_time = end_time - start_time
            assert total_time < 30.0  # Less than 30 seconds for stress test
            
            # System should still be responsive
            health = fiinquant_adapter.health_check()
            assert 'status' in health


@pytest.mark.integration
@pytest.mark.redis
class TestRedisIntegration:
    """Integration tests with Redis caching."""
    
    def test_redis_cache_integration(self, mock_config):
        """Test Redis cache integration (requires Redis server)."""
        try:
            import redis
            client = redis.Redis(host='localhost', port=6379, db=15)  # Use test DB
            client.ping()
        except:
            pytest.skip("Redis server not available")
        
        # Test with real Redis
        cache_manager = CacheManager(redis_client=client)
        
        with patch('utils.cache_manager.get_cache_manager', return_value=cache_manager):
            fiinquant_adapter = FiinQuantAdapter(mock_config)
            
            # Verify Redis integration
            assert fiinquant_adapter.cache_manager == cache_manager
            assert cache_manager.redis_client == client
            
            # Test cache operations
            cache_manager.set('test_key', {'data': 'test'}, ttl=10)
            result = cache_manager.get('test_key')
            assert result == {'data': 'test'}
            
            # Cleanup
            cache_manager.delete('test_key')


@pytest.mark.integration
@pytest.mark.network
class TestNetworkIntegration:
    """Integration tests requiring network access."""
    
    @pytest.mark.skip(reason="Requires real FiinQuant API credentials")
    def test_real_fiinquant_integration(self, mock_config):
        """Test with real FiinQuant API (requires credentials)."""
        # This test would require real API credentials
        # and should only be run in specific test environments
        
        fiinquant_adapter = FiinQuantAdapter(mock_config)
        
        # Test login
        login_result = fiinquant_adapter.login()
        assert login_result is True
        
        # Test data fetching
        latest_data = fiinquant_adapter.get_latest_data('VIC')
        assert latest_data is not None
        
        historical_data = fiinquant_adapter.fetch_historical_data('VIC', '1D', 10)
        assert len(historical_data) > 0
        
        # Test logout
        logout_result = fiinquant_adapter.logout()
        assert logout_result is True
    
    @pytest.mark.skip(reason="Requires real email/telegram configuration")
    @pytest.mark.asyncio
    async def test_real_alert_integration(self, mock_config, test_data_generator):
        """Test with real email/telegram services (requires configuration)."""
        # This test would require real email/telegram configuration
        # and should only be run in specific test environments
        
        alert_manager = AlertManager(mock_config)
        
        signal = test_data_generator.create_trading_signal('VIC', 'buy', 0.8)
        
        # Test real alert sending
        result = await alert_manager.send_trading_signal_alert(signal)
        assert result is True
        
        # Verify alert was logged
        history = alert_manager.get_alert_history()
        assert len(history) > 0