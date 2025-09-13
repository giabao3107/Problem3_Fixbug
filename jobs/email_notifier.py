"""Email notification system for trading alerts."""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging
import os
from jinja2 import Template


class EmailNotifier:
    """Email notification service for trading alerts."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize email notifier with configuration.
        
        Args:
            config: Email configuration dictionary
        """
        self.config = config.get('email', {})
        self.smtp_server = self.config.get('smtp_server', 'smtp.gmail.com')
        self.smtp_port = self.config.get('smtp_port', 587)
        self.sender_email = self.config.get('sender_email', '')
        self.sender_password = self.config.get('sender_password', '')
        self.recipient_emails = self.config.get('recipient_emails', [])
        
        # Email templates
        self.templates = {
            'buy_alert': self._get_buy_alert_template(),
            'sell_alert': self._get_sell_alert_template(),
            'risk_warning': self._get_risk_warning_template(),
            'daily_summary': self._get_daily_summary_template(),
            'portfolio_update': self._get_portfolio_update_template()
        }
        
        self.logger = logging.getLogger(__name__)
        
        # Validate configuration
        self._validate_config()
    
    def _validate_config(self):
        """Validate email configuration."""
        if not self.sender_email:
            raise ValueError("Sender email is required")
        if not self.sender_password:
            raise ValueError("Sender password is required")
        if not self.recipient_emails:
            raise ValueError("At least one recipient email is required")
    
    def send_buy_alert(self, buy_recommendations: List[Dict[str, Any]]) -> bool:
        """
        Send buy alert email.
        
        Args:
            buy_recommendations: List of buy recommendations
            
        Returns:
            bool: True if email sent successfully
        """
        if not buy_recommendations:
            return True
        
        subject = f"🟢 Trading Alert: {len(buy_recommendations)} Buy Recommendations - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        template = Template(self.templates['buy_alert'])
        html_content = template.render(
            recommendations=buy_recommendations,
            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            total_count=len(buy_recommendations)
        )
        
        return self._send_email(subject, html_content)
    
    def send_sell_alert(self, sell_recommendations: List[Dict[str, Any]]) -> bool:
        """
        Send sell alert email.
        
        Args:
            sell_recommendations: List of sell recommendations
            
        Returns:
            bool: True if email sent successfully
        """
        if not sell_recommendations:
            return True
        
        subject = f"🔴 Trading Alert: {len(sell_recommendations)} Sell Recommendations - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        template = Template(self.templates['sell_alert'])
        html_content = template.render(
            recommendations=sell_recommendations,
            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            total_count=len(sell_recommendations)
        )
        
        return self._send_email(subject, html_content)
    
    def send_risk_warning(self, risk_alerts: List[Dict[str, Any]]) -> bool:
        """
        Send risk warning email.
        
        Args:
            risk_alerts: List of risk alerts
            
        Returns:
            bool: True if email sent successfully
        """
        if not risk_alerts:
            return True
        
        subject = f"⚠️ Risk Warning: {len(risk_alerts)} Alerts - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        template = Template(self.templates['risk_warning'])
        html_content = template.render(
            alerts=risk_alerts,
            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            total_count=len(risk_alerts)
        )
        
        return self._send_email(subject, html_content)
    
    def send_daily_summary(self, summary_data: Dict[str, Any]) -> bool:
        """
        Send daily trading summary email.
        
        Args:
            summary_data: Daily summary data
            
        Returns:
            bool: True if email sent successfully
        """
        subject = f"📊 Daily Trading Summary - {datetime.now().strftime('%Y-%m-%d')}"
        
        template = Template(self.templates['daily_summary'])
        html_content = template.render(
            summary=summary_data,
            date=datetime.now().strftime('%Y-%m-%d'),
            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )
        
        return self._send_email(subject, html_content)
    
    def send_portfolio_update(self, portfolio_data: Dict[str, Any]) -> bool:
        """
        Send portfolio update email.
        
        Args:
            portfolio_data: Portfolio data
            
        Returns:
            bool: True if email sent successfully
        """
        subject = f"💼 Portfolio Update - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        template = Template(self.templates['portfolio_update'])
        html_content = template.render(
            portfolio=portfolio_data,
            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )
        
        return self._send_email(subject, html_content)
    
    def _send_email(self, subject: str, html_content: str, attachments: Optional[List[str]] = None) -> bool:
        """
        Send email with HTML content.
        
        Args:
            subject: Email subject
            html_content: HTML email content
            attachments: Optional list of file paths to attach
            
        Returns:
            bool: True if email sent successfully
        """
        try:
            # Create message
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = self.sender_email
            message["To"] = ", ".join(self.recipient_emails)
            
            # Add HTML content
            html_part = MIMEText(html_content, "html")
            message.attach(html_part)
            
            # Add attachments if provided
            if attachments:
                for file_path in attachments:
                    if os.path.exists(file_path):
                        with open(file_path, "rb") as attachment:
                            part = MIMEBase('application', 'octet-stream')
                            part.set_payload(attachment.read())
                        
                        encoders.encode_base64(part)
                        part.add_header(
                            'Content-Disposition',
                            f'attachment; filename= {os.path.basename(file_path)}'
                        )
                        message.attach(part)
            
            # Create secure connection and send email
            context = ssl.create_default_context()
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls(context=context)
                server.login(self.sender_email, self.sender_password)
                server.sendmail(self.sender_email, self.recipient_emails, message.as_string())
            
            self.logger.info(f"Email sent successfully: {subject}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send email: {str(e)}")
            return False
    
    def _get_buy_alert_template(self) -> str:
        """Get HTML template for buy alerts."""
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                .header { background-color: #4CAF50; color: white; padding: 15px; border-radius: 5px; }
                .content { margin: 20px 0; }
                .recommendation { border: 1px solid #ddd; margin: 10px 0; padding: 15px; border-radius: 5px; }
                .ticker { font-weight: bold; font-size: 18px; color: #2E7D32; }
                .confidence { background-color: #E8F5E8; padding: 5px 10px; border-radius: 3px; }
                .price { color: #1976D2; font-weight: bold; }
                .reason { color: #666; font-style: italic; }
                .footer { margin-top: 30px; font-size: 12px; color: #666; }
            </style>
        </head>
        <body>
            <div class="header">
                <h2>🟢 Buy Recommendations</h2>
                <p>{{ total_count }} stocks recommended for purchase</p>
            </div>
            
            <div class="content">
                {% for rec in recommendations %}
                <div class="recommendation">
                    <div class="ticker">{{ rec.ticker }}</div>
                    <p><strong>Action:</strong> {{ rec.action }}</p>
                    <p><strong>Confidence:</strong> <span class="confidence">{{ "%.1f" | format(rec.confidence * 100) }}%</span></p>
                    <p><strong>Entry Price:</strong> <span class="price">{{ "{:,.0f}".format(rec.entry_price) }} VND</span></p>
                    <p><strong>Stop Loss:</strong> <span class="price">{{ "{:,.0f}".format(rec.stop_loss) }} VND</span></p>
                    <p><strong>Take Profit:</strong> <span class="price">{{ "{:,.0f}".format(rec.take_profit) }} VND</span></p>
                    <p><strong>Position Size:</strong> {{ rec.position_size }}</p>
                    <p><strong>Risk/Reward:</strong> {{ "%.2f" | format(rec.risk_reward_ratio) }}</p>
                    <p class="reason"><strong>Reason:</strong> {{ rec.reason }}</p>
                </div>
                {% endfor %}
            </div>
            
            <div class="footer">
                <p>Generated at: {{ timestamp }}</p>
                <p>This is an automated trading alert. Please conduct your own analysis before making investment decisions.</p>
            </div>
        </body>
        </html>
        """
    
    def _get_sell_alert_template(self) -> str:
        """Get HTML template for sell alerts."""
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                .header { background-color: #F44336; color: white; padding: 15px; border-radius: 5px; }
                .content { margin: 20px 0; }
                .recommendation { border: 1px solid #ddd; margin: 10px 0; padding: 15px; border-radius: 5px; }
                .ticker { font-weight: bold; font-size: 18px; color: #C62828; }
                .confidence { background-color: #FFEBEE; padding: 5px 10px; border-radius: 3px; }
                .price { color: #1976D2; font-weight: bold; }
                .pnl-positive { color: #4CAF50; font-weight: bold; }
                .pnl-negative { color: #F44336; font-weight: bold; }
                .reason { color: #666; font-style: italic; }
                .footer { margin-top: 30px; font-size: 12px; color: #666; }
            </style>
        </head>
        <body>
            <div class="header">
                <h2>🔴 Sell Recommendations</h2>
                <p>{{ total_count }} positions recommended for sale</p>
            </div>
            
            <div class="content">
                {% for rec in recommendations %}
                <div class="recommendation">
                    <div class="ticker">{{ rec.ticker }}</div>
                    <p><strong>Action:</strong> {{ rec.action }}</p>
                    <p><strong>Confidence:</strong> <span class="confidence">{{ "%.1f" | format(rec.confidence * 100) }}%</span></p>
                    <p><strong>Current Price:</strong> <span class="price">{{ "{:,.0f}".format(rec.current_price) }} VND</span></p>
                    <p><strong>Entry Price:</strong> <span class="price">{{ "{:,.0f}".format(rec.entry_price) }} VND</span></p>
                    <p><strong>P&L:</strong> 
                        <span class="{% if rec.pnl_percent >= 0 %}pnl-positive{% else %}pnl-negative{% endif %}">
                            {{ "{:+.1f}".format(rec.pnl_percent * 100) }}%
                        </span>
                    </p>
                    <p><strong>Days Held:</strong> {{ rec.days_held }} days</p>
                    <p class="reason"><strong>Reason:</strong> {{ rec.reason }}</p>
                </div>
                {% endfor %}
            </div>
            
            <div class="footer">
                <p>Generated at: {{ timestamp }}</p>
                <p>This is an automated trading alert. Please conduct your own analysis before making investment decisions.</p>
            </div>
        </body>
        </html>
        """
    
    def _get_risk_warning_template(self) -> str:
        """Get HTML template for risk warnings."""
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                .header { background-color: #FF9800; color: white; padding: 15px; border-radius: 5px; }
                .content { margin: 20px 0; }
                .alert { border: 1px solid #ddd; margin: 10px 0; padding: 15px; border-radius: 5px; background-color: #FFF3E0; }
                .ticker { font-weight: bold; font-size: 18px; color: #E65100; }
                .confidence { background-color: #FFE0B2; padding: 5px 10px; border-radius: 3px; }
                .price { color: #1976D2; font-weight: bold; }
                .risk-factors { color: #D84315; font-weight: bold; }
                .footer { margin-top: 30px; font-size: 12px; color: #666; }
            </style>
        </head>
        <body>
            <div class="header">
                <h2>⚠️ Risk Warnings</h2>
                <p>{{ total_count }} risk alerts detected</p>
            </div>
            
            <div class="content">
                {% for alert in alerts %}
                <div class="alert">
                    <div class="ticker">{{ alert.ticker }}</div>
                    <p><strong>Alert Type:</strong> {{ alert.alert_type }}</p>
                    <p><strong>Confidence:</strong> <span class="confidence">{{ "%.1f" | format(alert.confidence * 100) }}%</span></p>
                    <p><strong>Current Price:</strong> <span class="price">{{ "{:,.0f}".format(alert.current_price) }} VND</span></p>
                    <p class="risk-factors"><strong>Risk Factors:</strong> {{ alert.risk_factors }}</p>
                </div>
                {% endfor %}
            </div>
            
            <div class="footer">
                <p>Generated at: {{ timestamp }}</p>
                <p>This is an automated risk alert. Please review your positions and consider appropriate risk management actions.</p>
            </div>
        </body>
        </html>
        """
    
    def _get_daily_summary_template(self) -> str:
        """Get HTML template for daily summary."""
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                .header { background-color: #2196F3; color: white; padding: 15px; border-radius: 5px; }
                .content { margin: 20px 0; }
                .stats { display: flex; flex-wrap: wrap; gap: 15px; }
                .stat-box { border: 1px solid #ddd; padding: 15px; border-radius: 5px; min-width: 200px; }
                .stat-value { font-size: 24px; font-weight: bold; color: #1976D2; }
                .stat-label { color: #666; }
                .footer { margin-top: 30px; font-size: 12px; color: #666; }
            </style>
        </head>
        <body>
            <div class="header">
                <h2>📊 Daily Trading Summary</h2>
                <p>{{ date }}</p>
            </div>
            
            <div class="content">
                <div class="stats">
                    <div class="stat-box">
                        <div class="stat-value">{{ summary.total_analyzed }}</div>
                        <div class="stat-label">Stocks Analyzed</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-value">{{ summary.buy_candidates }}</div>
                        <div class="stat-label">Buy Signals</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-value">{{ summary.sell_candidates }}</div>
                        <div class="stat-label">Sell Signals</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-value">{{ summary.risk_alerts }}</div>
                        <div class="stat-label">Risk Alerts</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-value">{{ "%.1f" | format(summary.avg_buy_confidence * 100) }}%</div>
                        <div class="stat-label">Avg Buy Confidence</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-value">{{ "%.1f" | format(summary.avg_sell_confidence * 100) }}%</div>
                        <div class="stat-label">Avg Sell Confidence</div>
                    </div>
                </div>
            </div>
            
            <div class="footer">
                <p>Generated at: {{ timestamp }}</p>
                <p>Daily summary of automated trading system activity.</p>
            </div>
        </body>
        </html>
        """
    
    def _get_portfolio_update_template(self) -> str:
        """Get HTML template for portfolio updates."""
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                .header { background-color: #9C27B0; color: white; padding: 15px; border-radius: 5px; }
                .content { margin: 20px 0; }
                .position { border: 1px solid #ddd; margin: 10px 0; padding: 15px; border-radius: 5px; }
                .ticker { font-weight: bold; font-size: 18px; color: #7B1FA2; }
                .weight { background-color: #F3E5F5; padding: 5px 10px; border-radius: 3px; }
                .price { color: #1976D2; font-weight: bold; }
                .footer { margin-top: 30px; font-size: 12px; color: #666; }
            </style>
        </head>
        <body>
            <div class="header">
                <h2>💼 Portfolio Update</h2>
                <p>{{ portfolio.total_positions }} positions | Avg Confidence: {{ "%.1f" | format(portfolio.avg_confidence * 100) }}%</p>
            </div>
            
            <div class="content">
                {% for position in portfolio.portfolio_allocation %}
                <div class="position">
                    <div class="ticker">{{ position.ticker }}</div>
                    <p><strong>Weight:</strong> <span class="weight">{{ "%.1f" | format(position.weight * 100) }}%</span></p>
                    <p><strong>Confidence:</strong> {{ "%.1f" | format(position.confidence * 100) }}%</p>
                    <p><strong>Entry Price:</strong> <span class="price">{{ "{:,.0f}".format(position.entry_price) }} VND</span></p>
                    <p><strong>Stop Loss:</strong> <span class="price">{{ "{:,.0f}".format(position.stop_loss) }} VND</span></p>
                    <p><strong>Take Profit:</strong> <span class="price">{{ "{:,.0f}".format(position.take_profit) }} VND</span></p>
                    <p><strong>Reason:</strong> {{ position.reason }}</p>
                </div>
                {% endfor %}
            </div>
            
            <div class="footer">
                <p>Generated at: {{ timestamp }}</p>
                <p>Portfolio allocation based on current trading signals and risk management rules.</p>
            </div>
        </body>
        </html>
        """