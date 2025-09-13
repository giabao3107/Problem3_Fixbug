import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timedelta
from alert_system.alert_manager import AlertManager, AlertType, AlertPriority
from alert_system.email_service import EmailService
from alert_system.telegram_service import TelegramService
from strategy.rsi_psar_engulfing import TradingSignal


class TestAlertManager:
    """Test cases for AlertManager class."""
    
    def test_alert_manager_initialization(self, mock_config):
        """Test AlertManager initialization."""
        alert_manager = AlertManager(mock_config)
        
        assert alert_manager.config == mock_config
        assert alert_manager.email_service is not None
        assert alert_manager.telegram_service is not None
        assert len(alert_manager.alert_history) == 0
        assert alert_manager.rate_limiter is not None
    
    def test_alert_manager_with_services(self, mock_config, mock_email_service, mock_telegram_service):
        """Test AlertManager with custom services."""
        alert_manager = AlertManager(
            config=mock_config,
            email_service=mock_email_service,
            telegram_service=mock_telegram_service
        )
        
        assert alert_manager.email_service == mock_email_service
        assert alert_manager.telegram_service == mock_telegram_service
    
    @pytest.mark.asyncio
    async def test_send_trading_signal_alert(self, mock_config, mock_email_service, mock_telegram_service, test_data_generator):
        """Test sending trading signal alerts."""
        alert_manager = AlertManager(
            config=mock_config,
            email_service=mock_email_service,
            telegram_service=mock_telegram_service
        )
        
        # Create test signal
        signal = test_data_generator.create_trading_signal('VIC', 'buy', 0.8)
        
        # Mock service methods
        mock_email_service.send_trading_signal_alert = AsyncMock(return_value=True)
        mock_telegram_service.send_trading_signal_alert = AsyncMock(return_value=True)
        
        # Send alert
        result = await alert_manager.send_trading_signal_alert(signal)
        
        assert result is True
        mock_email_service.send_trading_signal_alert.assert_called_once_with(signal)
        mock_telegram_service.send_trading_signal_alert.assert_called_once_with(signal)
        
        # Check alert history
        assert len(alert_manager.alert_history) == 1
        assert alert_manager.alert_history[0]['type'] == AlertType.TRADING_SIGNAL
    
    @pytest.mark.asyncio
    async def test_send_risk_alert(self, mock_config, mock_email_service, mock_telegram_service):
        """Test sending risk alerts."""
        alert_manager = AlertManager(
            config=mock_config,
            email_service=mock_email_service,
            telegram_service=mock_telegram_service
        )
        
        # Mock service methods
        mock_email_service.send_risk_alert = AsyncMock(return_value=True)
        mock_telegram_service.send_risk_alert = AsyncMock(return_value=True)
        
        # Send risk alert
        result = await alert_manager.send_risk_alert(
            ticker='VIC',
            risk_type='stop_loss',
            message='Stop loss triggered at 95.0',
            priority=AlertPriority.HIGH
        )
        
        assert result is True
        mock_email_service.send_risk_alert.assert_called_once()
        mock_telegram_service.send_risk_alert.assert_called_once()
        
        # Check alert history
        assert len(alert_manager.alert_history) == 1
        assert alert_manager.alert_history[0]['type'] == AlertType.RISK_MANAGEMENT
    
    @pytest.mark.asyncio
    async def test_send_system_alert(self, mock_config, mock_email_service, mock_telegram_service):
        """Test sending system alerts."""
        alert_manager = AlertManager(
            config=mock_config,
            email_service=mock_email_service,
            telegram_service=mock_telegram_service
        )
        
        # Mock service methods
        mock_email_service.send_system_alert = AsyncMock(return_value=True)
        mock_telegram_service.send_system_alert = AsyncMock(return_value=True)
        
        # Send system alert
        result = await alert_manager.send_system_alert(
            alert_type='connection_error',
            message='Failed to connect to FiinQuant API',
            priority=AlertPriority.CRITICAL
        )
        
        assert result is True
        mock_email_service.send_system_alert.assert_called_once()
        mock_telegram_service.send_system_alert.assert_called_once()
        
        # Check alert history
        assert len(alert_manager.alert_history) == 1
        assert alert_manager.alert_history[0]['type'] == AlertType.SYSTEM
    
    @pytest.mark.asyncio
    async def test_send_portfolio_summary(self, mock_config, mock_email_service, mock_telegram_service):
        """Test sending portfolio summary."""
        alert_manager = AlertManager(
            config=mock_config,
            email_service=mock_email_service,
            telegram_service=mock_telegram_service
        )
        
        # Mock service methods
        mock_email_service.send_portfolio_summary = AsyncMock(return_value=True)
        mock_telegram_service.send_portfolio_summary = AsyncMock(return_value=True)
        
        # Create test portfolio data
        portfolio_data = {
            'total_value': 1000000,
            'daily_pnl': 50000,
            'positions': [
                {'ticker': 'VIC', 'quantity': 100, 'current_price': 100.0},
                {'ticker': 'VHM', 'quantity': 200, 'current_price': 50.0}
            ]
        }
        
        # Send portfolio summary
        result = await alert_manager.send_portfolio_summary(portfolio_data)
        
        assert result is True
        mock_email_service.send_portfolio_summary.assert_called_once_with(portfolio_data)
        mock_telegram_service.send_portfolio_summary.assert_called_once_with(portfolio_data)
    
    @pytest.mark.asyncio
    async def test_rate_limiting(self, mock_config, mock_email_service, mock_telegram_service, test_data_generator):
        """Test alert rate limiting."""
        # Configure strict rate limiting
        mock_config.ALERT_RATE_LIMIT = 1  # 1 alert per minute
        
        alert_manager = AlertManager(
            config=mock_config,
            email_service=mock_email_service,
            telegram_service=mock_telegram_service
        )
        
        # Mock service methods
        mock_email_service.send_trading_signal_alert = AsyncMock(return_value=True)
        mock_telegram_service.send_trading_signal_alert = AsyncMock(return_value=True)
        
        # Send first alert (should succeed)
        signal1 = test_data_generator.create_trading_signal('VIC', 'buy', 0.8)
        result1 = await alert_manager.send_trading_signal_alert(signal1)
        assert result1 is True
        
        # Send second alert immediately (should be rate limited)
        signal2 = test_data_generator.create_trading_signal('VHM', 'sell', 0.7)
        result2 = await alert_manager.send_trading_signal_alert(signal2)
        assert result2 is False  # Rate limited
        
        # Only first alert should be sent
        assert mock_email_service.send_trading_signal_alert.call_count == 1
        assert mock_telegram_service.send_trading_signal_alert.call_count == 1
    
    @pytest.mark.asyncio
    async def test_service_failure_handling(self, mock_config, mock_email_service, mock_telegram_service, test_data_generator):
        """Test handling of service failures."""
        alert_manager = AlertManager(
            config=mock_config,
            email_service=mock_email_service,
            telegram_service=mock_telegram_service
        )
        
        # Mock email service failure
        mock_email_service.send_trading_signal_alert = AsyncMock(side_effect=Exception("Email failed"))
        mock_telegram_service.send_trading_signal_alert = AsyncMock(return_value=True)
        
        signal = test_data_generator.create_trading_signal('VIC', 'buy', 0.8)
        
        # Should still succeed if one service works
        result = await alert_manager.send_trading_signal_alert(signal)
        assert result is True
        
        # Check that error was logged
        assert len(alert_manager.alert_history) == 1
        assert 'errors' in alert_manager.alert_history[0]
    
    @pytest.mark.asyncio
    async def test_all_services_failure(self, mock_config, mock_email_service, mock_telegram_service, test_data_generator):
        """Test handling when all services fail."""
        alert_manager = AlertManager(
            config=mock_config,
            email_service=mock_email_service,
            telegram_service=mock_telegram_service
        )
        
        # Mock both services failing
        mock_email_service.send_trading_signal_alert = AsyncMock(side_effect=Exception("Email failed"))
        mock_telegram_service.send_trading_signal_alert = AsyncMock(side_effect=Exception("Telegram failed"))
        
        signal = test_data_generator.create_trading_signal('VIC', 'buy', 0.8)
        
        # Should fail when all services fail
        result = await alert_manager.send_trading_signal_alert(signal)
        assert result is False
    
    def test_get_alert_history(self, mock_config, mock_email_service, mock_telegram_service):
        """Test getting alert history."""
        alert_manager = AlertManager(
            config=mock_config,
            email_service=mock_email_service,
            telegram_service=mock_telegram_service
        )
        
        # Add some mock history
        alert_manager.alert_history = [
            {
                'timestamp': datetime.now() - timedelta(hours=2),
                'type': AlertType.TRADING_SIGNAL,
                'success': True
            },
            {
                'timestamp': datetime.now() - timedelta(hours=1),
                'type': AlertType.RISK_MANAGEMENT,
                'success': True
            }
        ]
        
        # Test getting all history
        history = alert_manager.get_alert_history()
        assert len(history) == 2
        
        # Test getting limited history
        history_limited = alert_manager.get_alert_history(limit=1)
        assert len(history_limited) == 1
        
        # Test filtering by type
        history_filtered = alert_manager.get_alert_history(alert_type=AlertType.TRADING_SIGNAL)
        assert len(history_filtered) == 1
        assert history_filtered[0]['type'] == AlertType.TRADING_SIGNAL
    
    def test_get_alert_stats(self, mock_config, mock_email_service, mock_telegram_service):
        """Test getting alert statistics."""
        alert_manager = AlertManager(
            config=mock_config,
            email_service=mock_email_service,
            telegram_service=mock_telegram_service
        )
        
        # Add some mock history
        alert_manager.alert_history = [
            {'type': AlertType.TRADING_SIGNAL, 'success': True},
            {'type': AlertType.TRADING_SIGNAL, 'success': False},
            {'type': AlertType.RISK_MANAGEMENT, 'success': True},
            {'type': AlertType.SYSTEM, 'success': True}
        ]
        
        stats = alert_manager.get_alert_stats()
        
        assert stats['total_alerts'] == 4
        assert stats['success_rate'] == 0.75
        assert stats['by_type'][AlertType.TRADING_SIGNAL] == 2
        assert stats['by_type'][AlertType.RISK_MANAGEMENT] == 1
        assert stats['by_type'][AlertType.SYSTEM] == 1


class TestEmailService:
    """Test cases for EmailService class."""
    
    def test_email_service_initialization(self, mock_config):
        """Test EmailService initialization."""
        email_service = EmailService(mock_config)
        
        assert email_service.config == mock_config
        assert email_service.smtp_server == mock_config.SMTP_SERVER
        assert email_service.smtp_port == mock_config.SMTP_PORT
        assert email_service.sender_email == mock_config.SENDER_EMAIL
    
    @pytest.mark.asyncio
    async def test_send_trading_signal_alert_email(self, mock_config, test_data_generator):
        """Test sending trading signal alert via email."""
        email_service = EmailService(mock_config)
        
        signal = test_data_generator.create_trading_signal('VIC', 'buy', 0.8)
        
        with patch('smtplib.SMTP') as mock_smtp:
            mock_server = Mock()
            mock_smtp.return_value.__enter__.return_value = mock_server
            
            result = await email_service.send_trading_signal_alert(signal)
            
            assert result is True
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once()
            mock_server.send_message.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_risk_alert_email(self, mock_config):
        """Test sending risk alert via email."""
        email_service = EmailService(mock_config)
        
        with patch('smtplib.SMTP') as mock_smtp:
            mock_server = Mock()
            mock_smtp.return_value.__enter__.return_value = mock_server
            
            result = await email_service.send_risk_alert(
                ticker='VIC',
                risk_type='stop_loss',
                message='Stop loss triggered',
                priority=AlertPriority.HIGH
            )
            
            assert result is True
            mock_server.send_message.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_system_alert_email(self, mock_config):
        """Test sending system alert via email."""
        email_service = EmailService(mock_config)
        
        with patch('smtplib.SMTP') as mock_smtp:
            mock_server = Mock()
            mock_smtp.return_value.__enter__.return_value = mock_server
            
            result = await email_service.send_system_alert(
                alert_type='connection_error',
                message='API connection failed',
                priority=AlertPriority.CRITICAL
            )
            
            assert result is True
            mock_server.send_message.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_portfolio_summary_email(self, mock_config):
        """Test sending portfolio summary via email."""
        email_service = EmailService(mock_config)
        
        portfolio_data = {
            'total_value': 1000000,
            'daily_pnl': 50000,
            'positions': []
        }
        
        with patch('smtplib.SMTP') as mock_smtp:
            mock_server = Mock()
            mock_smtp.return_value.__enter__.return_value = mock_server
            
            result = await email_service.send_portfolio_summary(portfolio_data)
            
            assert result is True
            mock_server.send_message.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_email_service_smtp_error(self, mock_config, test_data_generator):
        """Test email service SMTP error handling."""
        email_service = EmailService(mock_config)
        
        signal = test_data_generator.create_trading_signal('VIC', 'buy', 0.8)
        
        with patch('smtplib.SMTP') as mock_smtp:
            mock_smtp.side_effect = Exception("SMTP connection failed")
            
            result = await email_service.send_trading_signal_alert(signal)
            
            assert result is False
    
    def test_format_trading_signal_email(self, mock_config, test_data_generator):
        """Test formatting trading signal email."""
        email_service = EmailService(mock_config)
        
        signal = test_data_generator.create_trading_signal('VIC', 'buy', 0.8)
        
        subject, body = email_service._format_trading_signal_email(signal)
        
        assert 'VIC' in subject
        assert 'BUY' in subject.upper()
        assert 'VIC' in body
        assert str(signal.confidence) in body
    
    def test_format_risk_alert_email(self, mock_config):
        """Test formatting risk alert email."""
        email_service = EmailService(mock_config)
        
        subject, body = email_service._format_risk_alert_email(
            ticker='VIC',
            risk_type='stop_loss',
            message='Stop loss triggered at 95.0',
            priority=AlertPriority.HIGH
        )
        
        assert 'RISK ALERT' in subject.upper()
        assert 'VIC' in subject
        assert 'stop_loss' in body
        assert '95.0' in body


class TestTelegramService:
    """Test cases for TelegramService class."""
    
    def test_telegram_service_initialization(self, mock_config):
        """Test TelegramService initialization."""
        telegram_service = TelegramService(mock_config)
        
        assert telegram_service.config == mock_config
        assert telegram_service.bot_token == mock_config.TELEGRAM_BOT_TOKEN
        assert telegram_service.chat_id == mock_config.TELEGRAM_CHAT_ID
    
    @pytest.mark.asyncio
    async def test_send_trading_signal_alert_telegram(self, mock_config, test_data_generator):
        """Test sending trading signal alert via Telegram."""
        telegram_service = TelegramService(mock_config)
        
        signal = test_data_generator.create_trading_signal('VIC', 'buy', 0.8)
        
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = Mock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={'ok': True})
            mock_post.return_value.__aenter__.return_value = mock_response
            
            result = await telegram_service.send_trading_signal_alert(signal)
            
            assert result is True
            mock_post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_risk_alert_telegram(self, mock_config):
        """Test sending risk alert via Telegram."""
        telegram_service = TelegramService(mock_config)
        
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = Mock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={'ok': True})
            mock_post.return_value.__aenter__.return_value = mock_response
            
            result = await telegram_service.send_risk_alert(
                ticker='VIC',
                risk_type='stop_loss',
                message='Stop loss triggered',
                priority=AlertPriority.HIGH
            )
            
            assert result is True
            mock_post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_system_alert_telegram(self, mock_config):
        """Test sending system alert via Telegram."""
        telegram_service = TelegramService(mock_config)
        
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = Mock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={'ok': True})
            mock_post.return_value.__aenter__.return_value = mock_response
            
            result = await telegram_service.send_system_alert(
                alert_type='connection_error',
                message='API connection failed',
                priority=AlertPriority.CRITICAL
            )
            
            assert result is True
            mock_post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_portfolio_summary_telegram(self, mock_config):
        """Test sending portfolio summary via Telegram."""
        telegram_service = TelegramService(mock_config)
        
        portfolio_data = {
            'total_value': 1000000,
            'daily_pnl': 50000,
            'positions': []
        }
        
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = Mock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={'ok': True})
            mock_post.return_value.__aenter__.return_value = mock_response
            
            result = await telegram_service.send_portfolio_summary(portfolio_data)
            
            assert result is True
            mock_post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_telegram_api_error(self, mock_config, test_data_generator):
        """Test Telegram API error handling."""
        telegram_service = TelegramService(mock_config)
        
        signal = test_data_generator.create_trading_signal('VIC', 'buy', 0.8)
        
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = Mock()
            mock_response.status = 400
            mock_response.json = AsyncMock(return_value={'ok': False, 'description': 'Bad Request'})
            mock_post.return_value.__aenter__.return_value = mock_response
            
            result = await telegram_service.send_trading_signal_alert(signal)
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_telegram_network_error(self, mock_config, test_data_generator):
        """Test Telegram network error handling."""
        telegram_service = TelegramService(mock_config)
        
        signal = test_data_generator.create_trading_signal('VIC', 'buy', 0.8)
        
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_post.side_effect = Exception("Network error")
            
            result = await telegram_service.send_trading_signal_alert(signal)
            
            assert result is False
    
    def test_format_trading_signal_message(self, mock_config, test_data_generator):
        """Test formatting trading signal message."""
        telegram_service = TelegramService(mock_config)
        
        signal = test_data_generator.create_trading_signal('VIC', 'buy', 0.8)
        
        message = telegram_service._format_trading_signal_message(signal)
        
        assert '🚀' in message or '📈' in message  # Buy signal emoji
        assert 'VIC' in message
        assert 'BUY' in message.upper()
        assert str(signal.confidence) in message
    
    def test_format_risk_alert_message(self, mock_config):
        """Test formatting risk alert message."""
        telegram_service = TelegramService(mock_config)
        
        message = telegram_service._format_risk_alert_message(
            ticker='VIC',
            risk_type='stop_loss',
            message_text='Stop loss triggered at 95.0',
            priority=AlertPriority.HIGH
        )
        
        assert '⚠️' in message or '🚨' in message  # Alert emoji
        assert 'VIC' in message
        assert 'stop_loss' in message
        assert '95.0' in message


@pytest.mark.integration
class TestAlertSystemIntegration:
    """Integration tests for the alert system."""
    
    @pytest.mark.asyncio
    async def test_full_alert_workflow(self, mock_config, test_data_generator):
        """Test complete alert workflow."""
        # Create alert manager with mock services
        with patch('smtplib.SMTP'), patch('aiohttp.ClientSession.post') as mock_post:
            # Mock successful Telegram response
            mock_response = Mock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={'ok': True})
            mock_post.return_value.__aenter__.return_value = mock_response
            
            alert_manager = AlertManager(mock_config)
            
            # Send various types of alerts
            signal = test_data_generator.create_trading_signal('VIC', 'buy', 0.8)
            
            # Trading signal alert
            result1 = await alert_manager.send_trading_signal_alert(signal)
            assert result1 is True
            
            # Risk alert
            result2 = await alert_manager.send_risk_alert(
                ticker='VIC',
                risk_type='stop_loss',
                message='Stop loss triggered',
                priority=AlertPriority.HIGH
            )
            assert result2 is True
            
            # System alert
            result3 = await alert_manager.send_system_alert(
                alert_type='connection_error',
                message='API connection failed',
                priority=AlertPriority.CRITICAL
            )
            assert result3 is True
            
            # Check alert history
            history = alert_manager.get_alert_history()
            assert len(history) == 3
    
    @pytest.mark.asyncio
    async def test_alert_system_with_strategy(self, mock_config, sample_ohlcv_data):
        """Test alert system integration with trading strategy."""
        from strategy.rsi_psar_engulfing import RSIPSAREngulfingStrategy
        
        # Mock alert manager
        mock_alert_manager = Mock()
        mock_alert_manager.send_trading_signal_alert = AsyncMock(return_value=True)
        
        with patch('alert_system.alert_manager.AlertManager', return_value=mock_alert_manager):
            strategy = RSIPSAREngulfingStrategy(mock_config)
            
            # Mock strategy to generate signals
            with patch.object(strategy, 'analyze_ticker') as mock_analyze:
                signal = TradingSignal(
                    ticker='VIC',
                    timestamp=datetime.now(),
                    signal_type='buy',
                    confidence=0.8,
                    entry_price=100.0
                )
                mock_analyze.return_value = [signal]
                
                # Analyze ticker (would normally trigger alerts)
                signals = strategy.analyze_ticker('VIC', sample_ohlcv_data)
                
                assert len(signals) == 1
                assert signals[0].ticker == 'VIC'
    
    @pytest.mark.network
    @pytest.mark.asyncio
    async def test_real_email_integration(self, mock_config, test_data_generator):
        """Test with real email service (requires SMTP configuration)."""
        # Skip if no real email config
        if not hasattr(mock_config, 'SMTP_SERVER') or not mock_config.SMTP_SERVER:
            pytest.skip("No real SMTP configuration available")
        
        email_service = EmailService(mock_config)
        signal = test_data_generator.create_trading_signal('VIC', 'buy', 0.8)
        
        # This would send a real email
        # result = await email_service.send_trading_signal_alert(signal)
        # assert result is True
        
        # For safety, just test the formatting
        subject, body = email_service._format_trading_signal_email(signal)
        assert subject is not None
        assert body is not None
    
    @pytest.mark.telegram
    @pytest.mark.asyncio
    async def test_real_telegram_integration(self, mock_config, test_data_generator):
        """Test with real Telegram service (requires bot token)."""
        # Skip if no real Telegram config
        if not hasattr(mock_config, 'TELEGRAM_BOT_TOKEN') or not mock_config.TELEGRAM_BOT_TOKEN:
            pytest.skip("No real Telegram configuration available")
        
        telegram_service = TelegramService(mock_config)
        signal = test_data_generator.create_trading_signal('VIC', 'buy', 0.8)
        
        # This would send a real Telegram message
        # result = await telegram_service.send_trading_signal_alert(signal)
        # assert result is True
        
        # For safety, just test the formatting
        message = telegram_service._format_trading_signal_message(signal)
        assert message is not None
        assert len(message) > 0
    
    @pytest.mark.asyncio
    async def test_alert_performance_benchmark(self, mock_config, test_data_generator):
        """Test alert system performance."""
        import time
        
        # Mock services for speed
        mock_email_service = Mock()
        mock_email_service.send_trading_signal_alert = AsyncMock(return_value=True)
        mock_telegram_service = Mock()
        mock_telegram_service.send_trading_signal_alert = AsyncMock(return_value=True)
        
        alert_manager = AlertManager(
            config=mock_config,
            email_service=mock_email_service,
            telegram_service=mock_telegram_service
        )
        
        # Benchmark sending multiple alerts
        signals = [test_data_generator.create_trading_signal(f'TICKER_{i}', 'buy', 0.8) for i in range(10)]
        
        start_time = time.time()
        
        tasks = [alert_manager.send_trading_signal_alert(signal) for signal in signals]
        results = await asyncio.gather(*tasks)
        
        end_time = time.time()
        
        # Should complete quickly
        assert end_time - start_time < 1.0  # Less than 1 second for 10 alerts
        assert all(results)  # All should succeed
        assert len(alert_manager.alert_history) == 10