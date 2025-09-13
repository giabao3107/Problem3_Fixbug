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
        # Get base config from YAML
        email_config = self.config.get('alerts', {}).get('email', {})
        
        # Override with environment variables
        email_config.update({
            'sender_email': os.getenv('EMAIL_SENDER', email_config.get('sender_email', '')),
            'sender_password': os.getenv('EMAIL_PASSWORD', email_config.get('sender_password', '')),
            'smtp_server': os.getenv('EMAIL_SMTP_SERVER', email_config.get('smtp_server', 'smtp.gmail.com')),
            'smtp_port': int(os.getenv('EMAIL_SMTP_PORT', email_config.get('smtp_port', 587))),
        })
        
        # Parse recipient emails from environment
        recipients_env = os.getenv('EMAIL_RECIPIENTS', '')
        if recipients_env:
            email_config['recipient_emails'] = [email.strip() for email in recipients_env.split(',') if email.strip()]
        
        return email_config
    
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
        Send daily summary email.
        
        Args:
            summary_data: Daily summary data
            force: Force send even if already sent today
            
        Returns:
            bool: True if email sent successfully
        """
        if not self._should_send_daily_summary(force):
            return False
        
        try:
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