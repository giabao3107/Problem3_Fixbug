"""Main Orchestrator for Real-time Alert System.

Coordinates all components including data loading, strategy analysis,
email notifications, telegram alerts, and automated trading recommendations.
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import pandas as pd
import schedule
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from pathlib import Path
import json

# Import project modules
from utils.helpers import (
    load_config, load_symbols, setup_logging, is_trading_hours,
    get_env_variable, save_to_csv, DataCache, CircuitBreaker
)
from utils.fiinquant_adapter import FiinQuantAdapter
from strategy.rsi_psar_engulfing import RSIPSAREngulfingStrategy, TradingSignal
from jobs.telegram_bot import TradingTelegramBot
from jobs.email_service import get_email_service
from database.data_manager import DatabaseManager


class MainOrchestrator:
    """
    Main orchestrator that coordinates all system components.
    Manages data flow from loading to notifications and automated recommendations.
    """
    
    def __init__(self, config_path: str = "config/config.yaml"):
        """
        Initialize main orchestrator.
        
        Args:
            config_path: Path to configuration file
        """
        # Load configuration
        self.config = load_config(config_path)
        
        # Setup logging
        self.logger = setup_logging(self.config)
        self.logger.info("Initializing Main Orchestrator")
        
        # Initialize components
        self._initialize_components()
        
        # Runtime state
        self.is_running = False
        self.last_update_time = None
        self.update_count = 0
        self.error_count = 0
        
        # Performance tracking
        self.processing_times = []
        self.signal_counts = {'buy': 0, 'sell': 0, 'risk_warning': 0}
        self.daily_stats = {
            'total_analyzed': 0,
            'buy_signals': 0,
            'sell_signals': 0,
            'risk_alerts': 0,
            'emails_sent': 0,
            'telegram_messages': 0
        }
        
        # Circuit breaker for error handling
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=300  # 5 minutes
        )
        
        # Automated strategy data
        self.current_recommendations = {
            'buy_list': [],
            'sell_list': [],
            'risk_alerts': [],
            'portfolio_updates': [],
            'last_updated': None
        }
        
        # Setup graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _initialize_components(self):
        """Initialize all system components."""
        try:
            # Data adapter - FiinQuant
            username = get_env_variable('FIINQUANT_USERNAME', required=True)
            password = get_env_variable('FIINQUANT_PASSWORD', required=True)
            
            self.logger.info("Initializing FiinQuant data adapter")
            data_config = self.config.get('data_source', {})
            self.data_adapter = FiinQuantAdapter(
                username=username,
                password=password,
                retry_attempts=data_config.get('retry_attempts', 3),
                retry_delay=data_config.get('retry_delay', 5)
            )
            
            # Trading strategy
            self.strategy = RSIPSAREngulfingStrategy(self.config)
            
            # Notification services
            self.telegram_bot = TradingTelegramBot(self.config)
            self.email_service = get_email_service()
            
            # Database manager
            self.db_manager = DatabaseManager(self.config)
            
            # Symbol universe
            symbols = load_symbols()
            
            # Use all symbols from all exchanges if available
            if symbols.get('universe', {}).get('all_exchanges_list'):
                self.universe = symbols.get('universe', {}).get('all_exchanges_list', [])
                self.logger.info(f"Monitoring ALL symbols from HOSE, HNX, UPCOM: {len(self.universe)} symbols")
            else:
                # Fallback to VN30 if all symbols are not available
                self.universe = symbols.get('universe', {}).get('vn30', [])
                self.logger.info(f"Monitoring VN30 symbols: {len(self.universe)} symbols")
            
            # Cache for data
            self.data_cache = DataCache(default_ttl=300)  # 5 minutes
            
            # Configuration
            self.refresh_interval = int(get_env_variable('REFRESH_INTERVAL_SECONDS', 60))
            self.timeframe = get_env_variable('TIMEFRAME', '15m')
            
            # Automated strategy settings
            strategy_config = self.config.get('strategy', {})
            self.auto_strategy_enabled = strategy_config.get('automated_generation', True)
            self.portfolio_size = strategy_config.get('portfolio_size', 10)
            self.risk_tolerance = strategy_config.get('risk_tolerance', 'medium')
            
            self.logger.info("All components initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize components: {str(e)}")
            raise
    
    async def start(self):
        """Start the main orchestrator."""
        self.logger.info("Starting Main Orchestrator")
        
        try:
            # Initialize database
            await self.db_manager.initialize()
            
            # Initialize data adapter
            if not self.data_adapter.login():
                raise Exception("Failed to login to data source")
            
            # Initialize notification services
            await self.telegram_bot.initialize()
            await self.telegram_bot.start_bot()
            
            # Test email service
            email_test = self.email_service.test_email_connection()
            if email_test['success']:
                self.logger.info("Email service initialized successfully")
            else:
                self.logger.warning(f"Email service issue: {email_test['message']}")
            
            # Send startup notification
            startup_message = (
                f"🚀 Main Orchestrator Started\n\n"
                f"📊 Monitoring: {len(self.universe)} symbols\n"
                f"⏱️ Timeframe: {self.timeframe}\n"
                f"🔄 Refresh: {self.refresh_interval}s\n"
                f"🤖 Auto Strategy: {'✅' if self.auto_strategy_enabled else '❌'}\n"
                f"📧 Email Service: {'✅' if email_test['success'] else '❌'}\n"
                f"💼 Portfolio Size: {self.portfolio_size}"
            )
            
            await self.telegram_bot.send_system_alert(startup_message, "info")
            
            # Set running flag
            self.is_running = True
            
            # Schedule periodic tasks
            self._setup_schedules()
            
            # Start main monitoring loop
            await self._main_loop()
            
        except Exception as e:
            self.logger.error(f"Failed to start orchestrator: {str(e)}")
            await self._shutdown()
            raise
    
    def _setup_schedules(self):
        """Setup scheduled tasks."""
        # Main data update and analysis
        schedule.every(self.refresh_interval).seconds.do(self._schedule_update)
        
        # Automated strategy generation every 30 minutes during trading hours
        schedule.every(30).minutes.do(self._schedule_strategy_generation)
        
        # Health check every 5 minutes
        schedule.every(5).minutes.do(self._schedule_health_check)
        
        # Daily summary at market close (17:00)
        schedule.every().day.at("17:00").do(self._schedule_daily_summary)
        
        # Portfolio update every 2 hours during trading hours
        schedule.every(2).hours.do(self._schedule_portfolio_update)
        
        # Daily cleanup at midnight
        schedule.every().day.at("00:01").do(self._schedule_daily_cleanup)
        
        # Performance report every hour
        schedule.every().hour.do(self._schedule_performance_report)
        
        self.logger.info("Scheduled tasks configured")
    
    def _schedule_update(self):
        """Scheduled data update and analysis wrapper."""
        try:
            if is_trading_hours(self.config):
                asyncio.create_task(self._update_and_analyze_cycle())
        except Exception as e:
            self.logger.error(f"Scheduled update error: {str(e)}")
    
    def _schedule_strategy_generation(self):
        """Scheduled automated strategy generation."""
        try:
            if is_trading_hours(self.config) and self.auto_strategy_enabled:
                asyncio.create_task(self._generate_automated_strategy())
        except Exception as e:
            self.logger.error(f"Scheduled strategy generation error: {str(e)}")
    
    def _schedule_health_check(self):
        """Scheduled health check."""
        try:
            self._log_health_status()
        except Exception as e:
            self.logger.error(f"Health check error: {str(e)}")
    
    def _schedule_daily_summary(self):
        """Scheduled daily summary."""
        try:
            asyncio.create_task(self._send_daily_summary())
        except Exception as e:
            self.logger.error(f"Daily summary error: {str(e)}")
    
    def _schedule_portfolio_update(self):
        """Scheduled portfolio update."""
        try:
            if is_trading_hours(self.config):
                asyncio.create_task(self._send_portfolio_update())
        except Exception as e:
            self.logger.error(f"Portfolio update error: {str(e)}")
    
    def _schedule_daily_cleanup(self):
        """Daily cleanup tasks."""
        try:
            asyncio.create_task(self._daily_cleanup())
        except Exception as e:
            self.logger.error(f"Daily cleanup error: {str(e)}")
    
    def _schedule_performance_report(self):
        """Scheduled performance report."""
        try:
            asyncio.create_task(self._send_performance_report())
        except Exception as e:
            self.logger.error(f"Performance report error: {str(e)}")
    
    async def _main_loop(self):
        """Main monitoring loop."""
        self.logger.info("Starting main monitoring loop")
        
        while self.is_running:
            try:
                # Run scheduled tasks
                schedule.run_pending()
                
                # Check email service for daily summary
                if self.email_service.enabled:
                    self.email_service.check_and_send_daily_summary(self._get_daily_summary_data())
                
                # Sleep for a short interval
                await asyncio.sleep(1)
                
            except Exception as e:
                self.logger.error(f"Main loop error: {str(e)}")
                self.error_count += 1
                
                # If too many errors, pause briefly
                if self.error_count > 10:
                    self.logger.warning("Too many errors, pausing for 30 seconds")
                    await asyncio.sleep(30)
                    self.error_count = 0
    
    async def _update_and_analyze_cycle(self):
        """Perform data update and analysis cycle."""
        if not self.circuit_breaker.can_execute():
            self.logger.warning("Circuit breaker open, skipping update cycle")
            return
        
        start_time = time.time()
        
        try:
            self.logger.info("Starting update and analysis cycle")
            
            # Perform the update cycle
            signals = await self._perform_update_cycle()
            
            # Process signals and send notifications
            if signals:
                await self._process_signals_and_notify(signals)
            
            # Update statistics
            self.update_count += 1
            self.last_update_time = datetime.now()
            
            # Track processing time
            processing_time = time.time() - start_time
            self.processing_times.append(processing_time)
            
            # Keep only last 100 processing times
            if len(self.processing_times) > 100:
                self.processing_times = self.processing_times[-100:]
            
            self.circuit_breaker.record_success()
            
            self.logger.info(f"Update cycle completed in {processing_time:.2f}s, found {len(signals)} signals")
            
        except Exception as e:
            self.logger.error(f"Update cycle failed: {str(e)}")
            self.logger.error(traceback.format_exc())
            self.error_count += 1
            self.circuit_breaker.record_failure()
    
    async def _perform_update_cycle(self) -> List[TradingSignal]:
        """Perform the actual data update and analysis."""
        all_signals = []
        
        # Process tickers in batches for better performance
        batch_size = 20
        ticker_batches = [self.universe[i:i + batch_size] for i in range(0, len(self.universe), batch_size)]
        
        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=4) as executor:
            batch_futures = [
                executor.submit(self._process_ticker_batch, batch)
                for batch in ticker_batches
            ]
            
            for future in as_completed(batch_futures):
                try:
                    batch_signals = future.result(timeout=30)
                    all_signals.extend(batch_signals)
                except Exception as e:
                    self.logger.error(f"Batch processing failed: {str(e)}")
        
        # Update daily stats
        self.daily_stats['total_analyzed'] += len(self.universe)
        
        return all_signals
    
    def _process_ticker_batch(self, tickers: List[str]) -> List[TradingSignal]:
        """Process a batch of tickers."""
        signals = []
        
        for ticker in tickers:
            try:
                ticker_signals = self._analyze_ticker(ticker)
                signals.extend(ticker_signals)
            except Exception as e:
                self.logger.error(f"Failed to analyze {ticker}: {str(e)}")
        
        return signals
    
    def _analyze_ticker(self, ticker: str) -> List[TradingSignal]:
        """Analyze a single ticker for trading signals."""
        try:
            # Check cache first
            cache_key = f"data_{ticker}_{self.timeframe}"
            data = self.data_cache.get(cache_key)
            
            if data is None:
                # Fetch fresh data
                data = self.data_adapter.get_historical_data(
                    symbol=ticker,
                    timeframe=self.timeframe,
                    limit=200
                )
                
                if data is None or data.empty:
                    return []
                
                # Cache the data
                self.data_cache.set(cache_key, data)
            
            # Analyze with strategy
            signals = self.strategy.analyze(data, ticker)
            
            return signals
            
        except Exception as e:
            self.logger.error(f"Analysis failed for {ticker}: {str(e)}")
            return []
    
    async def _process_signals_and_notify(self, signals: List[TradingSignal]):
        """Process signals and send notifications."""
        if not signals:
            return
        
        # Categorize signals
        buy_signals = [s for s in signals if s.signal_type == 'buy']
        sell_signals = [s for s in signals if s.signal_type == 'sell']
        risk_signals = [s for s in signals if s.signal_type == 'risk_warning']
        
        # Update signal counts
        self.signal_counts['buy'] += len(buy_signals)
        self.signal_counts['sell'] += len(sell_signals)
        self.signal_counts['risk_warning'] += len(risk_signals)
        
        # Update daily stats
        self.daily_stats['buy_signals'] += len(buy_signals)
        self.daily_stats['sell_signals'] += len(sell_signals)
        self.daily_stats['risk_alerts'] += len(risk_signals)
        
        # Send Telegram notifications
        notification_tasks = []
        
        for signal in signals:
            # Save to database
            await self.db_manager.save_signal(signal)
            
            # Save to CSV
            self._save_signal_to_csv(signal)
            
            # Send Telegram notification
            notification_tasks.append(
                self.telegram_bot.send_trading_signal(signal)
            )
        
        # Execute all Telegram notifications
        if notification_tasks:
            await asyncio.gather(*notification_tasks, return_exceptions=True)
            self.daily_stats['telegram_messages'] += len(notification_tasks)
        
        # Send email notifications
        await self._send_email_notifications(buy_signals, sell_signals, risk_signals)
        
        self.logger.info(f"Processed {len(signals)} signals: {len(buy_signals)} buy, {len(sell_signals)} sell, {len(risk_signals)} risk")
    
    async def _send_email_notifications(self, buy_signals: List[TradingSignal], 
                                      sell_signals: List[TradingSignal], 
                                      risk_signals: List[TradingSignal]):
        """Send email notifications for signals."""
        if not self.email_service.enabled:
            return
        
        email_tasks = []
        
        # Convert signals to email format
        if buy_signals:
            buy_recommendations = [self._signal_to_email_format(s) for s in buy_signals]
            if self.email_service.send_buy_alerts(buy_recommendations):
                self.daily_stats['emails_sent'] += 1
        
        if sell_signals:
            sell_recommendations = [self._signal_to_email_format(s) for s in sell_signals]
            if self.email_service.send_sell_alerts(sell_recommendations):
                self.daily_stats['emails_sent'] += 1
        
        if risk_signals:
            risk_alerts = [self._signal_to_email_format(s) for s in risk_signals]
            if self.email_service.send_risk_warnings(risk_alerts):
                self.daily_stats['emails_sent'] += 1
    
    def _signal_to_email_format(self, signal: TradingSignal) -> Dict[str, Any]:
        """Convert TradingSignal to email format."""
        return {
            'symbol': signal.symbol,
            'signal_type': signal.signal_type,
            'confidence': signal.confidence,
            'price': signal.price,
            'timestamp': signal.timestamp.isoformat(),
            'reason': signal.reason,
            'indicators': signal.indicators
        }
    
    async def _generate_automated_strategy(self):
        """Generate automated trading strategy recommendations."""
        if not self.auto_strategy_enabled:
            return
        
        try:
            self.logger.info("Generating automated strategy recommendations")
            
            # Get recent signals from database
            recent_signals = await self.db_manager.get_recent_signals(hours=24)
            
            if not recent_signals:
                self.logger.info("No recent signals for strategy generation")
                return
            
            # Generate automated strategy using the strategy class
            strategy_data = self.strategy.generate_automated_strategy(
                recent_signals, 
                portfolio_size=self.portfolio_size,
                risk_tolerance=self.risk_tolerance
            )
            
            # Update current recommendations
            self.current_recommendations.update({
                'buy_list': strategy_data.get('buy_recommendations', []),
                'sell_list': strategy_data.get('sell_recommendations', []),
                'risk_alerts': strategy_data.get('risk_alerts', []),
                'portfolio_updates': strategy_data.get('portfolio_recommendations', []),
                'last_updated': datetime.now()
            })
            
            # Send strategy update via Telegram
            await self._send_strategy_update(strategy_data)
            
            self.logger.info("Automated strategy generated successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to generate automated strategy: {str(e)}")
    
    async def _send_strategy_update(self, strategy_data: Dict[str, Any]):
        """Send strategy update notifications."""
        try:
            buy_count = len(strategy_data.get('buy_recommendations', []))
            sell_count = len(strategy_data.get('sell_recommendations', []))
            risk_count = len(strategy_data.get('risk_alerts', []))
            
            message = (
                f"🤖 Automated Strategy Update\n\n"
                f"📈 Buy Recommendations: {buy_count}\n"
                f"📉 Sell Recommendations: {sell_count}\n"
                f"⚠️ Risk Alerts: {risk_count}\n"
                f"🕐 Updated: {datetime.now().strftime('%H:%M:%S')}"
            )
            
            await self.telegram_bot.send_system_alert(message, "info")
            
        except Exception as e:
            self.logger.error(f"Failed to send strategy update: {str(e)}")
    
    async def _send_portfolio_update(self):
        """Send portfolio update notifications."""
        try:
            if not self.current_recommendations['portfolio_updates']:
                return
            
            portfolio_data = {
                'recommendations': self.current_recommendations['portfolio_updates'],
                'last_updated': self.current_recommendations['last_updated'],
                'total_positions': len(self.current_recommendations['portfolio_updates']),
                'risk_level': self.risk_tolerance
            }
            
            # Send via email
            if self.email_service.enabled:
                self.email_service.send_portfolio_update(portfolio_data)
                self.daily_stats['emails_sent'] += 1
            
        except Exception as e:
            self.logger.error(f"Failed to send portfolio update: {str(e)}")
    
    def _save_signal_to_csv(self, signal: TradingSignal):
        """Save signal to CSV file."""
        try:
            # Create signals directory if it doesn't exist
            signals_dir = Path("data/signals")
            signals_dir.mkdir(parents=True, exist_ok=True)
            
            # Create filename with current date
            filename = f"signals_{datetime.now().strftime('%Y%m%d')}.csv"
            filepath = signals_dir / filename
            
            # Prepare signal data
            signal_data = {
                'timestamp': signal.timestamp,
                'symbol': signal.symbol,
                'signal_type': signal.signal_type,
                'confidence': signal.confidence,
                'price': signal.price,
                'reason': signal.reason,
                'rsi': signal.indicators.get('rsi'),
                'psar': signal.indicators.get('psar'),
                'engulfing': signal.indicators.get('engulfing_pattern')
            }
            
            # Save to CSV
            save_to_csv([signal_data], str(filepath))
            
        except Exception as e:
            self.logger.error(f"Failed to save signal to CSV: {str(e)}")
    
    def _log_health_status(self):
        """Log system health status."""
        try:
            avg_processing_time = (
                sum(self.processing_times) / len(self.processing_times)
                if self.processing_times else 0
            )
            
            health_status = {
                'status': 'healthy' if self.error_count < 5 else 'degraded',
                'uptime_minutes': (
                    (datetime.now() - self.last_update_time).total_seconds() / 60
                    if self.last_update_time else 0
                ),
                'update_count': self.update_count,
                'error_count': self.error_count,
                'avg_processing_time': round(avg_processing_time, 2),
                'signal_counts': self.signal_counts.copy(),
                'daily_stats': self.daily_stats.copy(),
                'email_service_status': self.email_service.get_email_stats() if self.email_service.enabled else 'disabled',
                'circuit_breaker_status': 'open' if not self.circuit_breaker.can_execute() else 'closed'
            }
            
            self.logger.info(f"Health Status: {json.dumps(health_status, indent=2)}")
            
        except Exception as e:
            self.logger.error(f"Health status check failed: {str(e)}")
    
    async def _send_performance_report(self):
        """Send performance report."""
        try:
            if not self.processing_times:
                return
            
            avg_time = sum(self.processing_times) / len(self.processing_times)
            max_time = max(self.processing_times)
            min_time = min(self.processing_times)
            
            report = (
                f"📊 Performance Report\n\n"
                f"⏱️ Avg Processing: {avg_time:.2f}s\n"
                f"📈 Max Processing: {max_time:.2f}s\n"
                f"📉 Min Processing: {min_time:.2f}s\n"
                f"🔄 Updates: {self.update_count}\n"
                f"❌ Errors: {self.error_count}\n"
                f"📧 Emails Sent: {self.daily_stats['emails_sent']}\n"
                f"💬 Telegram Messages: {self.daily_stats['telegram_messages']}"
            )
            
            await self.telegram_bot.send_system_alert(report, "info")
            
        except Exception as e:
            self.logger.error(f"Failed to send performance report: {str(e)}")
    
    def _get_daily_summary_data(self) -> Dict[str, Any]:
        """Get daily summary data for email."""
        return {
            'total_analyzed': self.daily_stats['total_analyzed'],
            'buy_candidates': self.daily_stats['buy_signals'],
            'sell_candidates': self.daily_stats['sell_signals'],
            'risk_alerts': self.daily_stats['risk_alerts'],
            'avg_buy_confidence': 0.75,  # This would be calculated from actual signals
            'avg_sell_confidence': 0.70,  # This would be calculated from actual signals
            'processing_performance': {
                'avg_time': sum(self.processing_times) / len(self.processing_times) if self.processing_times else 0,
                'update_count': self.update_count,
                'error_count': self.error_count
            },
            'current_recommendations': self.current_recommendations
        }
    
    async def _send_daily_summary(self):
        """Send daily summary."""
        try:
            summary_data = self._get_daily_summary_data()
            
            # Send via email
            if self.email_service.enabled:
                self.email_service.send_daily_summary(summary_data)
                self.daily_stats['emails_sent'] += 1
            
            # Send via Telegram
            summary_message = (
                f"📊 Daily Summary\n\n"
                f"📈 Analyzed: {summary_data['total_analyzed']} symbols\n"
                f"🟢 Buy Signals: {summary_data['buy_candidates']}\n"
                f"🔴 Sell Signals: {summary_data['sell_candidates']}\n"
                f"⚠️ Risk Alerts: {summary_data['risk_alerts']}\n"
                f"📧 Emails Sent: {self.daily_stats['emails_sent']}\n"
                f"💬 Messages Sent: {self.daily_stats['telegram_messages']}"
            )
            
            await self.telegram_bot.send_system_alert(summary_message, "info")
            
            # Reset daily stats
            self.daily_stats = {
                'total_analyzed': 0,
                'buy_signals': 0,
                'sell_signals': 0,
                'risk_alerts': 0,
                'emails_sent': 0,
                'telegram_messages': 0
            }
            
        except Exception as e:
            self.logger.error(f"Failed to send daily summary: {str(e)}")
    
    async def _daily_cleanup(self):
        """Perform daily cleanup tasks."""
        try:
            self.logger.info("Performing daily cleanup")
            
            # Clear old cache entries
            self.data_cache.clear_expired()
            
            # Reset error count
            self.error_count = 0
            
            # Clear old processing times
            self.processing_times = []
            
            # Reset email service daily summary flag
            if self.email_service.enabled:
                self.email_service.reset_daily_summary_flag()
            
            # Database cleanup
            await self.db_manager.cleanup_old_data(days=30)
            
            self.logger.info("Daily cleanup completed")
            
        except Exception as e:
            self.logger.error(f"Daily cleanup failed: {str(e)}")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum}, initiating shutdown")
        self.is_running = False
        
        # Create shutdown task
        asyncio.create_task(self._shutdown())
    
    async def _shutdown(self):
        """Gracefully shutdown the orchestrator."""
        self.logger.info("Shutting down Main Orchestrator")
        
        try:
            # Set running flag to False
            self.is_running = False
            
            # Send shutdown notification
            if hasattr(self, 'telegram_bot'):
                await self.telegram_bot.send_system_alert(
                    "📴 Main Orchestrator Shutting Down\n\n"
                    f"Uptime: {self.update_count} cycles\n"
                    f"Signals processed: {sum(self.signal_counts.values())}\n"
                    f"Emails sent: {self.daily_stats['emails_sent']}",
                    "warning"
                )
            
            # Cleanup components
            if hasattr(self, 'telegram_bot'):
                await self.telegram_bot.stop()
            
            if hasattr(self, 'db_manager'):
                await self.db_manager.close()
            
            if hasattr(self, 'data_adapter'):
                self.data_adapter.logout()
            
            self.logger.info("Main Orchestrator shutdown completed")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {str(e)}")
    
    def get_current_status(self) -> Dict[str, Any]:
        """Get current orchestrator status."""
        return {
            'is_running': self.is_running,
            'last_update': self.last_update_time.isoformat() if self.last_update_time else None,
            'update_count': self.update_count,
            'error_count': self.error_count,
            'signal_counts': self.signal_counts.copy(),
            'daily_stats': self.daily_stats.copy(),
            'current_recommendations': self.current_recommendations.copy(),
            'email_service_enabled': self.email_service.enabled,
            'auto_strategy_enabled': self.auto_strategy_enabled,
            'universe_size': len(self.universe),
            'circuit_breaker_open': not self.circuit_breaker.can_execute()
        }


async def main():
    """Main entry point for the orchestrator."""
    orchestrator = MainOrchestrator()
    
    try:
        await orchestrator.start()
    except KeyboardInterrupt:
        print("\n📴 Shutting down...")
    except Exception as e:
        logging.error(f"Orchestrator failed: {str(e)}")
        raise
    finally:
        await orchestrator._shutdown()


if __name__ == "__main__":
    asyncio.run(main())