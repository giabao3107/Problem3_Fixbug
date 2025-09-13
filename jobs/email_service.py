"""Email service integration for the realtime alert system."""

import os
import yaml
from typing import Dict, Any, List
from datetime import datetime, time
import logging
from threading import Lock

from jobs.email_notifier import EmailNotifier


class EmailService:
    """Email service wrapper for the realtime alert system."""
    
    def __init__(self, config_path: str = None):
        """
        Initialize email service.
        
        Args:
            config_path: Path to configuration file
        """
        self.config_path = config_path or "config/config.yaml"
        self.config = self._load_config()
        self.email_config = self._load_email_config()
        
        # Initialize email notifier if enabled
        self.notifier = None
        self.enabled = self.email_config.get('enabled', False)
        
        if self.enabled:
            try:
                self.notifier = EmailNotifier({'email': self.email_config})
                self.logger = logging.getLogger(__name__)
                self.logger.info("Email service initialized successfully")
            except Exception as e:
                self.logger = logging.getLogger(__name__)
                self.logger.error(f"Failed to initialize email service: {str(e)}")
                self.enabled = False
        
        # Rate limiting
        self._last_email_times = {}
        self._email_count_per_hour = {}
        self._lock = Lock()
        
        # Daily summary tracking
        self._daily_summary_sent = False
        self._last_summary_date = None
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as file:
                return yaml.safe_load(file)
        except Exception as e:
            logging.error(f"Failed to load config from {self.config_path}: {str(e)}")
            return {}
    
    def _load_email_config(self) -> Dict[str, Any]:
        """Load email configuration from config and environment variables."""
        email_config = self.config.get('email', {})
        smtp_config = email_config.get('smtp', {})
        credentials_config = email_config.get('credentials', {})
        
        # Get configuration with environment variable overrides
        config = {
            'smtp_server': os.getenv('SMTP_SERVER', smtp_config.get('server', 'smtp.gmail.com')),
            'smtp_port': int(os.getenv('SMTP_PORT', smtp_config.get('port', 587))),
            'sender_email': os.getenv('SENDER_EMAIL', credentials_config.get('sender_email', '')),
            'sender_password': os.getenv('SENDER_PASSWORD', credentials_config.get('sender_password', '')),
            'recipient_emails': self._parse_recipient_emails(
                os.getenv('RECIPIENT_EMAILS', ''),
                credentials_config.get('recipient_emails', [])
            ),
            'use_tls': os.getenv('EMAIL_USE_TLS', str(smtp_config.get('use_tls', True))).lower() == 'true'
        }
        
        return config
    
    def _parse_recipient_emails(self, env_emails: str, config_emails: List[str]) -> List[str]:
        """Parse recipient emails from environment variable or config."""
        if env_emails:
            return [email.strip() for email in env_emails.split(',') if email.strip()]
        return config_emails
    
    def _should_send_email(self, alert_type: str) -> bool:
        """Check if email should be sent based on rate limiting and configuration."""
        if not self.enabled or not self.notifier:
            return False
        
        # Check if alert type is enabled
        alert_types = self.config.get('alerts', {}).get('types', {})
        if not alert_types.get(alert_type, False):
            return False
        
        with self._lock:
            current_time = datetime.now()
            current_hour = current_time.replace(minute=0, second=0, microsecond=0)
            
            # Check debounce (minimum time between same alerts)
            debounce_minutes = self.email_config.get('debounce_minutes', 15)
            last_time = self._last_email_times.get(alert_type)
            
            if last_time:
                time_diff = (current_time - last_time).total_seconds() / 60
                if time_diff < debounce_minutes:
                    return False
            
            # Check hourly limit
            max_emails_per_hour = self.email_config.get('max_emails_per_hour', 10)
            hour_count = self._email_count_per_hour.get(current_hour, 0)
            
            if hour_count >= max_emails_per_hour:
                return False
            
            # Update tracking
            self._last_email_times[alert_type] = current_time
            self._email_count_per_hour[current_hour] = hour_count + 1
            
            # Clean old hour counts
            old_hours = [h for h in self._email_count_per_hour.keys() 
                        if (current_time - h).total_seconds() > 3600]
            for old_hour in old_hours:
                del self._email_count_per_hour[old_hour]
            
            return True
    
    def send_buy_alerts(self, buy_recommendations: List[Dict[str, Any]]) -> bool:
        """
        Send buy alert emails.
        
        Args:
            buy_recommendations: List of buy recommendations
            
        Returns:
            bool: True if email sent successfully
        """
        if not buy_recommendations or not self._should_send_email('buy_signal'):
            return False
        
        try:
            return self.notifier.send_buy_alert(buy_recommendations)
        except Exception as e:
            logging.error(f"Failed to send buy alert email: {str(e)}")
            return False
    
    def send_sell_alerts(self, sell_recommendations: List[Dict[str, Any]]) -> bool:
        """
        Send sell alert emails.
        
        Args:
            sell_recommendations: List of sell recommendations
            
        Returns:
            bool: True if email sent successfully
        """
        if not sell_recommendations or not self._should_send_email('sell_signal'):
            return False
        
        try:
            return self.notifier.send_sell_alert(sell_recommendations)
        except Exception as e:
            logging.error(f"Failed to send sell alert email: {str(e)}")
            return False
    
    def send_risk_warnings(self, risk_alerts: List[Dict[str, Any]]) -> bool:
        """
        Send risk warning emails.
        
        Args:
            risk_alerts: List of risk alerts
            
        Returns:
            bool: True if email sent successfully
        """
        if not risk_alerts or not self._should_send_email('risk_warning'):
            return False
        
        try:
            return self.notifier.send_risk_warning(risk_alerts)
        except Exception as e:
            logging.error(f"Failed to send risk warning email: {str(e)}")
            return False
    
    def send_daily_summary(self, summary_data: Dict[str, Any], force: bool = False) -> bool:
        """
        Send daily summary email with tomorrow's recommendations.
        
        Args:
            summary_data: Daily summary data
            force: Force send even if already sent today
            
        Returns:
            bool: True if email sent successfully
        """
        if not self._should_send_daily_summary(force):
            return False
        
        try:
            # Add tomorrow's recommendations to summary data
            summary_data = self._enhance_summary_with_recommendations(summary_data)
            
            success = self.notifier.send_daily_summary(summary_data)
            if success:
                self._daily_summary_sent = True
                self._last_summary_date = datetime.now().date()
            return success
        except Exception as e:
            logging.error(f"Failed to send daily summary email: {str(e)}")
            return False
    
    def send_portfolio_update(self, portfolio_data: Dict[str, Any]) -> bool:
        """
        Send portfolio update email.
        
        Args:
            portfolio_data: Portfolio data
            
        Returns:
            bool: True if email sent successfully
        """
        if not self._should_send_email('portfolio_update'):
            return False
        
        try:
            return self.notifier.send_portfolio_update(portfolio_data)
        except Exception as e:
            logging.error(f"Failed to send portfolio update email: {str(e)}")
            return False
    
    def _should_send_daily_summary(self, force: bool = False) -> bool:
        """Check if daily summary should be sent."""
        if not self.enabled or not self.notifier:
            return False
        
        # Check if daily summary is enabled
        if not self.email_config.get('send_daily_summary', True):
            return False
        
        if force:
            return True
        
        current_date = datetime.now().date()
        
        # Check if already sent today
        if (self._daily_summary_sent and 
            self._last_summary_date and 
            self._last_summary_date == current_date):
            return False
        
        # Check if it's time to send (default 17:00)
        summary_time_str = self.email_config.get('daily_summary_time', '17:00')
        try:
            summary_time = datetime.strptime(summary_time_str, '%H:%M').time()
            current_time = datetime.now().time()
            
            # Send if current time is past summary time and we haven't sent today
            if current_time >= summary_time:
                return True
        except ValueError:
            logging.error(f"Invalid daily_summary_time format: {summary_time_str}")
        
        return False
    
    def check_and_send_daily_summary(self, summary_data: Dict[str, Any]) -> bool:
        """
        Check if it's time to send daily summary and send if needed.
        
        Args:
            summary_data: Daily summary data
            
        Returns:
            bool: True if email was sent or not needed
        """
        if self._should_send_daily_summary():
            return self.send_daily_summary(summary_data)
        return True
    
    def reset_daily_summary_flag(self):
        """Reset daily summary flag (useful for testing or manual reset)."""
        self._daily_summary_sent = False
        self._last_summary_date = None
    
    def get_email_stats(self) -> Dict[str, Any]:
        """Get email service statistics."""
        current_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
        
        return {
            'enabled': self.enabled,
            'emails_sent_this_hour': self._email_count_per_hour.get(current_hour, 0),
            'max_emails_per_hour': self.email_config.get('max_emails_per_hour', 10),
            'daily_summary_sent_today': self._daily_summary_sent,
            'last_summary_date': self._last_summary_date.isoformat() if self._last_summary_date else None,
            'recipient_count': len(self.email_config.get('recipient_emails', [])),
            'last_email_times': {
                alert_type: time.isoformat() 
                for alert_type, time in self._last_email_times.items()
            }
        }
    
    def test_email_connection(self) -> Dict[str, Any]:
        """
        Test email connection and configuration.
        
        Returns:
            Dict with test results
        """
        if not self.enabled:
            return {
                'success': False,
                'message': 'Email service is disabled',
                'config_valid': False
            }
        
        if not self.notifier:
            return {
                'success': False,
                'message': 'Email notifier not initialized',
                'config_valid': False
            }
        
        # Test basic configuration
        config_issues = []
        if not self.email_config.get('sender_email'):
            config_issues.append('Missing sender email')
        if not self.email_config.get('sender_password'):
            config_issues.append('Missing sender password')
        if not self.email_config.get('recipient_emails'):
            config_issues.append('Missing recipient emails')
        
        if config_issues:
            return {
                'success': False,
                'message': f"Configuration issues: {', '.join(config_issues)}",
                'config_valid': False
            }
        
        # Test SMTP connection first
        try:
            import smtplib
            import ssl
            
            context = ssl.create_default_context()
            with smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port']) as server:
                if self.email_config.get('use_tls', True):
                    server.starttls(context=context)
                server.login(self.email_config['sender_email'], self.email_config['sender_password'])
            
        except Exception as e:
            return {
                'success': False,
                'message': f'SMTP connection failed: {str(e)}',
                'config_valid': True
            }
        
        # Try to send a test email
        try:
            test_data = {
                'total_analyzed': 0,
                'buy_candidates': 0,
                'sell_candidates': 0,
                'risk_alerts': 0,
                'avg_buy_confidence': 0.0,
                'avg_sell_confidence': 0.0
            }
            
            # Temporarily bypass rate limiting for test
            original_enabled = self.enabled
            self.enabled = True
            
            success = self.notifier.send_daily_summary(test_data)
            
            self.enabled = original_enabled
            
            return {
                'success': success,
                'message': 'Test email sent successfully' if success else 'Failed to send test email',
                'config_valid': True
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f'Test email failed: {str(e)}',
                'config_valid': True
            }
    
    def send_test_email(self) -> bool:
        """
        Send a test email to verify configuration.
        
        Returns:
            bool: True if test email sent successfully
        """
        if not self.enabled:
            return False
            
        try:
            test_subject = "Trading Alert System - Test Email"
            test_content = """
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #2E8B57;">🎯 Trading Alert System</h2>
                <p>This is a test email from your Trading Alert System.</p>
                <p><strong>✅ Email configuration is working correctly!</strong></p>
                <hr style="border: 1px solid #ddd; margin: 20px 0;">
                <p style="color: #666; font-size: 12px;">
                    If you received this email, your email notifications are properly configured.
                    You will now receive trading alerts and daily summaries.
                </p>
            </div>
            """
            
            return self.notifier._send_email(test_subject, test_content)
        except Exception as e:
            self.logger.error(f"Failed to send test email: {str(e)}")
            return False
    
    def _enhance_summary_with_recommendations(self, summary_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enhance summary data with tomorrow's trading recommendations.
        
        Args:
            summary_data: Original summary data
            
        Returns:
            Enhanced summary data with recommendations
        """
        try:
            from strategy.rsi_psar_engulfing import RSIPSAREngulfingStrategy
            from utils.fiinquant_adapter import FiinQuantAdapter
            import pandas as pd
            
            # Initialize strategy and adapter
            strategy = RSIPSAREngulfingStrategy()
            adapter = FiinQuantAdapter()
            
            # Get list of stocks to analyze (from config or default list)
            symbols = self.config.get('symbols', ['VIC', 'VHM', 'VRE', 'HPG', 'TCB', 'CTG', 'BID', 'VCB', 'MSN', 'MWG'])
            
            buy_recommendations = []
            sell_recommendations = []
            watch_list = []
            
            for symbol in symbols[:10]:  # Limit to top 10 for email
                try:
                    # Get recent data for analysis
                    df = adapter.get_historical_data(symbol, periods=100)
                    if df is None or len(df) < 50:
                        continue
                    
                    # Generate signal
                    signal = strategy.generate_signal(df, symbol)
                    if signal is None:
                        continue
                    
                    current_price = df['close'].iloc[-1]
                    
                    # Create recommendation based on signal
                    if signal.signal_type == 'BUY' and signal.confidence >= 0.6:
                        target_price = current_price * (1 + signal.confidence * 0.1)  # Estimate target
                        buy_recommendations.append({
                            'symbol': symbol,
                            'current_price': current_price,
                            'target_price': target_price,
                            'confidence': signal.confidence,
                            'reason': f"RSI: {signal.indicators.get('rsi', 0):.1f}, PSAR: {signal.indicators.get('psar_trend', 'N/A')}"
                        })
                    elif signal.signal_type == 'SELL' and signal.confidence >= 0.6:
                        target_price = current_price * (1 - signal.confidence * 0.1)  # Estimate target
                        sell_recommendations.append({
                            'symbol': symbol,
                            'current_price': current_price,
                            'target_price': target_price,
                            'confidence': signal.confidence,
                            'reason': f"RSI: {signal.indicators.get('rsi', 0):.1f}, PSAR: {signal.indicators.get('psar_trend', 'N/A')}"
                        })
                    elif signal.confidence >= 0.4:  # Add to watch list if moderate confidence
                        support = current_price * 0.95
                        resistance = current_price * 1.05
                        watch_list.append({
                            'symbol': symbol,
                            'current_price': current_price,
                            'key_levels': f"S: {support:,.0f} - R: {resistance:,.0f}",
                            'reason': f"Moderate signal strength, monitor for breakout"
                        })
                        
                except Exception as e:
                    self.logger.warning(f"Failed to analyze {symbol}: {str(e)}")
                    continue
            
            # Sort by confidence
            buy_recommendations.sort(key=lambda x: x['confidence'], reverse=True)
            sell_recommendations.sort(key=lambda x: x['confidence'], reverse=True)
            
            # Add recommendations to summary data
            summary_data['tomorrow_recommendations'] = {
                'buy_list': buy_recommendations[:5],  # Top 5 buy recommendations
                'sell_list': sell_recommendations[:5],  # Top 5 sell recommendations
                'watch_list': watch_list[:5]  # Top 5 watch list
            }
            
            self.logger.info(f"Generated {len(buy_recommendations)} buy, {len(sell_recommendations)} sell, {len(watch_list)} watch recommendations")
            
        except Exception as e:
            self.logger.error(f"Failed to generate tomorrow's recommendations: {str(e)}")
            # Add empty recommendations if generation fails
            summary_data['tomorrow_recommendations'] = {
                'buy_list': [],
                'sell_list': [],
                'watch_list': []
            }
        
        return summary_data


# Global email service instance
_email_service = None


def get_email_service(config_path: str = None) -> EmailService:
    """Get global email service instance."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService(config_path)
    return _email_service


def reset_email_service():
    """Reset global email service instance (useful for testing)."""
    global _email_service
    _email_service = None