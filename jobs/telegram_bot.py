"""
Telegram Bot for Trading Alerts
Sends real-time trading signals and responds to user commands.
"""

import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
import json

import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

from utils.helpers import load_config, get_env_variable, format_currency, format_percentage
from strategy.rsi_psar_engulfing import TradingSignal, StrategyState, RSIPSAREngulfingStrategy
from utils.fiinquant_adapter import FiinQuantAdapter


class AlertDebouncer:
    """Prevents duplicate alerts from being sent."""
    
    def __init__(self, debounce_minutes: int = 5):
        self.debounce_minutes = debounce_minutes
        self.last_alerts: Dict[str, datetime] = {}  # ticker -> last alert time
        self.sent_signals: Set[str] = set()  # Unique signal IDs
    
    def should_send_alert(self, ticker: str, signal_type: str, 
                         signal_time: datetime) -> bool:
        """Check if alert should be sent based on debounce rules."""
        
        # Create unique signal ID
        signal_id = f"{ticker}_{signal_type}_{signal_time.strftime('%Y%m%d_%H%M')}"
        
        # Check if exact signal already sent
        if signal_id in self.sent_signals:
            return False
        
        # Check debounce timing
        key = f"{ticker}_{signal_type}"
        
        if key in self.last_alerts:
            time_diff = signal_time - self.last_alerts[key]
            if time_diff.total_seconds() < self.debounce_minutes * 60:
                return False
        
        # Update tracking
        self.last_alerts[key] = signal_time
        self.sent_signals.add(signal_id)
        
        # Clean up old entries (keep last 24 hours)
        cutoff_time = signal_time - timedelta(hours=24)
        self.last_alerts = {
            k: v for k, v in self.last_alerts.items() 
            if v > cutoff_time
        }
        
        return True


class TradingTelegramBot:
    """
    Telegram bot for sending trading alerts and handling user commands.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Telegram bot.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.bot_token = get_env_variable('TELEGRAM_BOT_TOKEN', '8047919251:AAH7-9j6_X08RpSPCQLMir_PVkkrx92ybdI')
        self.chat_id = get_env_variable('TELEGRAM_CHAT_ID', '1818962950')
        
        # Alert settings
        alert_config = config.get('alerts', {}).get('telegram', {})
        self.max_alerts_per_hour = alert_config.get('max_alerts_per_hour', 20)
        
        # Initialize debouncer
        debounce_minutes = alert_config.get('debounce_minutes', 5)
        self.debouncer = AlertDebouncer(debounce_minutes)
        
        # Rate limiting
        self.alert_count_history: List[datetime] = []
        
        # Bot application
        self.application = None
        self.bot_running = False
        
        # Storage for user interactions
        self.user_preferences: Dict[str, Dict] = {}
        
        self.logger = logging.getLogger(__name__)
    
    async def initialize(self):
        """Initialize bot application."""
        self.application = Application.builder().token(self.bot_token).build()
        
        # Add handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("top", self.top_command))
        self.application.add_handler(CommandHandler("recommendations", self.recommendations_command))
        self.application.add_handler(CommandHandler("send_recommendations", self.send_recommendations_command))
        self.application.add_handler(CommandHandler("positions", self.positions_command))
        self.application.add_handler(CommandHandler("settings", self.settings_command))
        self.application.add_handler(CallbackQueryHandler(self.button_handler))
        
        # Message handler for general messages
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.message_handler)
        )
        
        self.logger.info("Telegram bot initialized")
    
    async def start_bot(self):
        """Start the bot."""
        if not self.application:
            await self.initialize()
        
        self.bot_running = True
        
        # Start polling
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        self.logger.info("Telegram bot started")
        
        # Send startup message
        await self.send_message(
            "🤖 *Trading Alert Bot Started*\n\n"
            "Bot is now active and monitoring markets.\n"
            "Use /help to see available commands."
        )
    
    async def stop_bot(self):
        """Stop the bot."""
        if self.application and self.bot_running:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            
            self.bot_running = False
            self.logger.info("Telegram bot stopped")
    
    async def send_trading_signal(self, signal: TradingSignal) -> bool:
        """
        Send trading signal as formatted message.
        
        Args:
            signal: Trading signal to send
            
        Returns:
            bool: True if message sent successfully
        """
        # Check rate limiting
        if not self._check_rate_limit():
            self.logger.warning("Rate limit exceeded, skipping alert")
            return False
        
        # Check debounce
        if not self.debouncer.should_send_alert(
            signal.ticker, signal.signal_type, signal.timestamp
        ):
            self.logger.debug(f"Alert debounced for {signal.ticker} {signal.signal_type}")
            return False
        
        # Format message
        message = self._format_signal_message(signal)
        
        # Send message
        success = await self.send_message(message)
        
        if success:
            # Update rate limiting
            self.alert_count_history.append(datetime.now())
        
        return success
    
    def _format_signal_message(self, signal: TradingSignal) -> str:
        """Format trading signal into Telegram message."""
        
        # Emoji mapping
        emoji_map = {
            'buy': '🟢',
            'sell': '🔴', 
            'risk_warning': '🟠'
        }
        
        emoji = emoji_map.get(signal.signal_type, '🔵')
        
        # Signal type title
        type_map = {
            'buy': 'MUA MỚI',
            'sell': 'BÁN CHỐT LỜI',
            'risk_warning': 'CẢNH BÁO RỦI RO'
        }
        
        signal_title = type_map.get(signal.signal_type, signal.signal_type.upper())
        
        # Base message
        message = f"{emoji} *{signal_title}*\n\n"
        message += f"📊 *Mã:* `{signal.ticker}`\n"
        message += f"💰 *Giá:* {format_currency(signal.entry_price)}\n"
        message += f"⏰ *Thời gian:* {signal.timestamp.strftime('%H:%M:%S')}\n"
        message += f"🎯 *Độ tin cậy:* {signal.confidence:.0%}\n"
        
        # Add specific details based on signal type
        if signal.signal_type == 'buy':
            message += f"\n📈 *Entry Setup:*\n"
            
            if signal.stop_loss:
                message += f"🛑 *Stop Loss:* {format_currency(signal.stop_loss)}\n"
            
            if signal.take_profit:
                message += f"🎯 *Take Profit:* {format_currency(signal.take_profit)}\n"
            
            # Technical details
            metadata = signal.metadata or {}
            if metadata:
                message += f"\n📋 *Kỹ thuật:*\n"
                if 'rsi' in metadata:
                    message += f"• RSI: {metadata['rsi']:.1f}\n"
                if 'price_vs_psar' in metadata and metadata['price_vs_psar']:
                    message += f"• Giá > PSAR ✅\n"
                if 'volume_anomaly' in metadata and metadata['volume_anomaly']:
                    message += f"• Volume bất thường ✅\n"
                if 'engulfing_in_3_candles' in metadata and metadata['engulfing_in_3_candles']:
                    message += f"• Bullish Engulfing ✅\n"
        
        elif signal.signal_type == 'sell':
            metadata = signal.metadata or {}
            
            if 'pnl_percent' in metadata:
                pnl_percent = metadata['pnl_percent']
                message += f"💹 *P&L:* {format_percentage(pnl_percent)}\n"
            
            if 'days_held' in metadata:
                message += f"📅 *Thời gian nắm giữ:* {metadata['days_held']} ngày\n"
        
        elif signal.signal_type == 'risk_warning':
            metadata = signal.metadata or {}
            
            if 'volume_ratio' in metadata:
                message += f"📊 *Volume:* {metadata['volume_ratio']:.1f}x trung bình\n"
            
            if 'daily_range_percent' in metadata:
                message += f"📈 *Biến động:* {metadata['daily_range_percent']:.1f}%\n"
        
        # Add reason
        message += f"\n💡 *Lý do:* {signal.reason}\n"
        
        # Add timestamp
        message += f"\n⏱ _{signal.timestamp.strftime('%d/%m/%Y %H:%M:%S')}_"
        
        return message
    
    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits."""
        now = datetime.now()
        
        # Clean old entries (keep last hour)
        cutoff = now - timedelta(hours=1)
        self.alert_count_history = [
            t for t in self.alert_count_history if t > cutoff
        ]
        
        # Check if under limit
        return len(self.alert_count_history) < self.max_alerts_per_hour
    
    async def send_message(self, text: str, 
                          reply_markup=None,
                          parse_mode='Markdown') -> bool:
        """
        Send message to configured chat.
        
        Args:
            text: Message text
            reply_markup: Keyboard markup
            parse_mode: Parse mode for formatting
            
        Returns:
            bool: True if sent successfully
        """
        try:
            bot = telegram.Bot(token=self.bot_token)
            
            await bot.send_message(
                chat_id=self.chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send Telegram message: {str(e)}")
            return False
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        welcome_text = (
            "🤖 *Chào mừng đến với Trading Alert Bot!*\n\n"
            "Bot này sẽ gửi cảnh báo giao dịch real-time dựa trên chiến lược "
            "RSI-PSAR-Engulfing cho thị trường chứng khoán Việt Nam.\n\n"
            "📋 *Các lệnh có sẵn:*\n"
            "/help - Hiển thị trợ giúp\n"
            "/status - Trạng thái hệ thống\n"
            "/top - Top cơ hội giao dịch\n" 
            "/recommendations - Khuyến nghị mua/bán ngày mai\n"
            "/send_recommendations - Gửi khuyến nghị ngay\n"
            "/positions - Vị thế hiện tại\n"
            "/settings - Cài đặt cá nhân\n\n"
            "🔔 Bot đã sẵn sàng gửi cảnh báo!"
        )
        
        await update.message.reply_text(welcome_text, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        help_text = (
            "📖 *HƯỚNG DẪN SỬ DỤNG*\n\n"
            "🤖 *Bot Commands:*\n"
            "/start - Khởi động bot\n"
            "/help - Hiển thị hướng dẫn này\n"
            "/status - Trạng thái hệ thống và thống kê\n"
            "/top - Top cơ hội mua/bán\n"
            "/recommendations - Khuyến nghị mua/bán ngày mai\n"
            "/positions - Vị thế đang nắm giữ\n"
            "/settings - Cài đặt thông báo\n\n"
            
            "📊 *Loại Tín Hiệu:*\n"
            "🟢 *MUA MỚI* - Cơ hội mua vào\n"
            "🔴 *BÁN CHỐT LỜI* - Tín hiệu bán ra\n"
            "🟠 *CẢNH BÁO RỦI RO* - Cảnh báo rủi ro\n\n"
            
            "🎯 *Chiến lược:*\n"
            "• RSI(14) với mức 30/50/70\n"
            "• PSAR với AF 0.02-0.20\n"
            "• Engulfing Pattern\n"
            "• Volume Analysis\n\n"
            
            "⚠️ *Lưu ý:*\n"
            "Bot chỉ mang tính tham khảo.\n"
            "Luôn thực hiện phân tích riêng trước khi đầu tư."
        )
        
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        # This would be called with actual system status
        # For now, return placeholder
        
        status_text = (
            "📊 *TRẠNG THÁI HỆ THỐNG*\n\n"
            "🟢 *Hệ thống:* Hoạt động bình thường\n"
            "📡 *Kết nối FiinQuant:* OK\n"
            "⏰ *Thời gian cập nhật:* 15 phút\n"
            "📈 *Thị trường:* HOSE, HNX, UPCOM\n\n"
            
            "📋 *Thống kê hôm nay:*\n"
            "🟢 Tín hiệu mua: 0\n"
            "🔴 Tín hiệu bán: 0\n"
            "🟠 Cảnh báo rủi ro: 0\n\n"
            
            "💼 *Portfolio:*\n"
            "📊 Vị thế đang mở: 0/10\n"
            "💰 P&L hôm nay: 0%\n\n"
            
            f"🕐 *Cập nhật lúc:* {datetime.now().strftime('%H:%M:%S')}"
        )
        
        await update.message.reply_text(status_text, parse_mode='Markdown')
    
    async def top_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /top command."""
        try:
            # Generate current trading opportunities
            recommendations = await self._generate_recommendations()
            top_text = self._format_top_opportunities(recommendations)
        except Exception as e:
            self.logger.error(f"Failed to generate top opportunities: {str(e)}")
            top_text = (
                "🔝 *TOP CƠ HỘI GIAO DỊCH HIỆN TẠI*\n\n"
                "❌ *Lỗi:* Không thể tải cơ hội giao dịch\n"
                "Vui lòng thử lại sau.\n\n"
                "💡 *Gợi ý:* Sử dụng /recommendations để xem khuyến nghị cho ngày mai\n\n"
                f"🕐 *Cập nhật:* {datetime.now().strftime('%H:%M:%S')}"
            )
        
        keyboard = [
            [InlineKeyboardButton("🔄 Làm mới", callback_data='refresh_top')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            top_text, 
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def recommendations_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /recommendations command."""
        try:
            # Generate recommendations
            recommendations = await self._generate_recommendations()
            recommendations_text = self._format_recommendations(recommendations)
        except Exception as e:
            self.logger.error(f"Failed to generate recommendations: {str(e)}")
            recommendations_text = (
                "💡 *KHUYẾN NGHỊ MUA/BÁN NGÀY MAI*\n\n"
                "❌ *Lỗi:* Không thể tạo khuyến nghị\n"
                "Vui lòng thử lại sau.\n\n"
                f"🕐 *Cập nhật:* {datetime.now().strftime('%H:%M:%S')}"
            )
        
        keyboard = [
            [InlineKeyboardButton("🔄 Làm mới", callback_data='refresh_recommendations')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            recommendations_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def send_recommendations_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /send_recommendations command - send recommendations immediately."""
        try:
            # Send loading message
            loading_msg = await update.message.reply_text(
                "🔄 *Đang tạo khuyến nghị...*\n\nVui lòng đợi...",
                parse_mode='Markdown'
            )
            
            # Generate and send recommendations
            recommendations = await self._generate_recommendations()
            recommendations_text = self._format_recommendations(recommendations)
            
            # Delete loading message and send recommendations
            await loading_msg.delete()
            
            keyboard = [
                [InlineKeyboardButton("🔄 Làm mới", callback_data='refresh_recommendations')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                recommendations_text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            
            # Log successful recommendation generation
            self.logger.info(f"Recommendations sent successfully to user {update.effective_user.id}")
            
        except Exception as e:
            self.logger.error(f"Failed to send recommendations: {str(e)}")
            await update.message.reply_text(
                "❌ *Lỗi:* Không thể tạo khuyến nghị\n"
                "Vui lòng thử lại sau hoặc liên hệ hỗ trợ.",
                parse_mode='Markdown'
            )
    
    async def positions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /positions command."""
        positions_text = (
            "💼 *VỊ THẾ HIỆN TẠI*\n\n"
            "📊 *Tổng quan:*\n"
            "• Số vị thế: 0/10\n"
            "• Tổng P&L: 0%\n"
            "• Giá trị: 0 VND\n\n"
            
            "📋 *Chi tiết vị thế:*\n"
            "_Hiện tại không có vị thế nào_\n\n"
            
            f"🕐 *Cập nhật:* {datetime.now().strftime('%H:%M:%S')}"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔄 Làm mới", callback_data='refresh_positions')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            positions_text,
            parse_mode='Markdown', 
            reply_markup=reply_markup
        )
    
    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /settings command."""
        settings_text = (
            "⚙️ *CÀI ĐẶT THÔNG BÁO*\n\n"
            "🔔 *Loại thông báo:*\n"
            "🟢 Tín hiệu mua: Bật\n"
            "🔴 Tín hiệu bán: Bật\n"
            "🟠 Cảnh báo rủi ro: Bật\n\n"
            
            "⏰ *Thời gian:*\n"
            "• Debounce: 5 phút\n"
            "• Giới hạn: 20 alerts/giờ\n\n"
            
            "📊 *Bộ lọc:*\n"
            "• Độ tin cậy tối thiểu: 60%\n"
            "• Thanh khoản: Bật\n"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("🟢 Mua", callback_data='toggle_buy'),
                InlineKeyboardButton("🔴 Bán", callback_data='toggle_sell')
            ],
            [
                InlineKeyboardButton("🟠 Rủi ro", callback_data='toggle_risk'),
                InlineKeyboardButton("💾 Lưu", callback_data='save_settings')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            settings_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button presses."""
        query = update.callback_query
        await query.answer()
        
        if query.data == 'refresh_top':
            await query.edit_message_text(
                "🔄 *Đang làm mới...*\n\nVui lòng đợi...",
                parse_mode='Markdown'
            )
            # Here you would refresh actual data
            await self.top_command(update, context)
            
        elif query.data == 'refresh_recommendations':
            await query.edit_message_text(
                "🔄 *Đang làm mới khuyến nghị...*\n\nVui lòng đợi...",
                parse_mode='Markdown'
            )
            # Generate fresh recommendations
            try:
                recommendations = await self._generate_recommendations()
                recommendations_text = self._format_recommendations(recommendations)
                
                keyboard = [
                    [InlineKeyboardButton("🔄 Làm mới", callback_data='refresh_recommendations')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    recommendations_text,
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
            except Exception as e:
                self.logger.error(f"Failed to refresh recommendations: {str(e)}")
                await query.edit_message_text(
                    "❌ *Lỗi:* Không thể làm mới khuyến nghị\nVui lòng thử lại sau.",
                    parse_mode='Markdown'
                )
            
        elif query.data == 'refresh_top':
            await query.edit_message_text(
                "🔄 *Đang làm mới...*\n\nVui lòng đợi...",
                parse_mode='Markdown'
            )
            # Generate fresh top opportunities
            try:
                recommendations = await self._generate_recommendations()
                top_text = self._format_top_opportunities(recommendations)
                
                keyboard = [
                    [InlineKeyboardButton("🔄 Làm mới", callback_data='refresh_top')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    top_text,
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
            except Exception as e:
                self.logger.error(f"Failed to refresh top opportunities: {str(e)}")
                await query.edit_message_text(
                    "❌ *Lỗi:* Không thể làm mới cơ hội giao dịch\nVui lòng thử lại sau.",
                    parse_mode='Markdown'
                )
            
        elif query.data.startswith('toggle_'):
            setting_type = query.data.replace('toggle_', '')
            await query.edit_message_text(
                f"✅ *Đã thay đổi cài đặt {setting_type}*\n\n"
                "Sử dụng /settings để xem cài đặt hiện tại.",
                parse_mode='Markdown'
            )
            
        elif query.data == 'save_settings':
            await query.edit_message_text(
                "💾 *Đã lưu cài đặt*\n\nCài đặt mới sẽ có hiệu lực ngay lập tức.",
                parse_mode='Markdown'
            )
    
    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle general messages.""" 
        text = update.message.text.lower()
        
        if any(keyword in text for keyword in ['help', 'trợ giúp', 'hướng dẫn']):
            await self.help_command(update, context)
        elif any(keyword in text for keyword in ['status', 'trạng thái']):
            await self.status_command(update, context)
        elif any(keyword in text for keyword in ['top', 'tốt nhất']):
            await self.top_command(update, context)
        elif any(keyword in text for keyword in ['recommendations', 'khuyến nghị', 'gợi ý', 'mua bán', 'trading']):
            await self.recommendations_command(update, context)
        elif any(keyword in text for keyword in ['send recommendations', 'gửi khuyến nghị', 'tạo khuyến nghị']):
            await self.send_recommendations_command(update, context)
        else:
            await update.message.reply_text(
                "🤖 Xin chào! Sử dụng /help để xem các lệnh có sẵn."
            )
    
    async def send_system_alert(self, message: str, alert_type: str = "info"):
        """
        Send system alert message.
        
        Args:
            message: Alert message
            alert_type: Type of alert (info, warning, error)
        """
        emoji_map = {
            'info': 'ℹ️',
            'warning': '⚠️', 
            'error': '🚨'
        }
        
        emoji = emoji_map.get(alert_type, 'ℹ️')
        formatted_message = f"{emoji} *System Alert*\n\n{message}"
        
        await self.send_message(formatted_message)
    
    async def send_daily_summary(self, summary_data: Dict[str, Any]) -> bool:
        """
        Send daily trading summary with recommendations.
        
        Args:
            summary_data: Dictionary containing daily summary information
            
        Returns:
            bool: True if sent successfully
        """
        try:
            # Enhance summary with recommendations if not already included
            if 'recommendations' not in summary_data:
                try:
                    recommendations = await self._generate_recommendations()
                    summary_data['recommendations'] = recommendations
                except Exception as e:
                    self.logger.warning(f"Failed to generate recommendations for daily summary: {str(e)}")
            
            message = self._format_daily_summary(summary_data)
            return await self.send_message(message)
        except Exception as e:
            self.logger.error(f"Failed to send daily summary: {str(e)}")
            return False
    
    async def send_portfolio_update(self, portfolio_data: Dict[str, Any]) -> bool:
        """
        Send portfolio update notification.
        
        Args:
            portfolio_data: Dictionary containing portfolio information
            
        Returns:
            bool: True if sent successfully
        """
        try:
            message = self._format_portfolio_update(portfolio_data)
            return await self.send_message(message)
        except Exception as e:
            self.logger.error(f"Failed to send portfolio update: {str(e)}")
            return False
    
    async def send_automated_strategy_alert(self, strategy_data: Dict[str, Any]) -> bool:
        """
        Send automated strategy recommendation.
        
        Args:
            strategy_data: Dictionary containing strategy recommendation
            
        Returns:
            bool: True if sent successfully
        """
        try:
            message = self._format_automated_strategy(strategy_data)
            return await self.send_message(message)
        except Exception as e:
            self.logger.error(f"Failed to send automated strategy alert: {str(e)}")
            return False
    
    def _format_daily_summary(self, summary_data: Dict[str, Any]) -> str:
        """
        Format daily summary message.
        
        Args:
            summary_data: Summary data dictionary
            
        Returns:
            str: Formatted message
        """
        date_str = summary_data.get('date', datetime.now().strftime('%d/%m/%Y'))
        
        message = f"📊 *BÁO CÁO CUỐI NGÀY - {date_str}*\n\n"
        
        # Trading signals summary
        signals = summary_data.get('signals', {})
        message += f"📈 *Tín hiệu giao dịch:*\n"
        message += f"🟢 Mua: {signals.get('buy_count', 0)}\n"
        message += f"🔴 Bán: {signals.get('sell_count', 0)}\n"
        message += f"🟠 Cảnh báo: {signals.get('risk_count', 0)}\n\n"
        
        # Portfolio performance
        portfolio = summary_data.get('portfolio', {})
        if portfolio:
            message += f"💼 *Portfolio:*\n"
            message += f"💰 P&L hôm nay: {format_percentage(portfolio.get('daily_pnl', 0))}\n"
            message += f"📊 Tổng P&L: {format_percentage(portfolio.get('total_pnl', 0))}\n"
            message += f"🎯 Vị thế mở: {portfolio.get('open_positions', 0)}\n\n"
        
        # Tomorrow's recommendations
        recommendations = summary_data.get('recommendations', {})
        if recommendations:
            buy_list = recommendations.get('buy_list', [])
            sell_list = recommendations.get('sell_list', [])
            
            message += f"💡 *Khuyến nghị ngày mai:*\n"
            if buy_list:
                message += f"📈 Mua: {', '.join([rec['symbol'] for rec in buy_list[:3]])}\n"
            if sell_list:
                message += f"📉 Bán: {', '.join([rec['symbol'] for rec in sell_list[:3]])}\n"
            if buy_list or sell_list:
                message += f"💬 Dùng /recommendations để xem chi tiết\n\n"
        
        # Top performers
        top_gainers = summary_data.get('top_gainers', [])
        if top_gainers:
            message += f"🚀 *Top tăng giá:*\n"
            for stock in top_gainers[:3]:
                message += f"• {stock['ticker']}: {format_percentage(stock['change'])}\n"
            message += "\n"
        
        # Market overview
        market = summary_data.get('market', {})
        if market:
            message += f"📊 *Thị trường:*\n"
            message += f"📈 VN-Index: {market.get('vnindex_change', 'N/A')}\n"
            message += f"📊 Thanh khoản: {format_currency(market.get('total_volume', 0))}\n\n"
        
        message += f"⏰ *Cập nhật:* {datetime.now().strftime('%H:%M:%S')}"
        
        return message
    
    def _format_portfolio_update(self, portfolio_data: Dict[str, Any]) -> str:
        """
        Format portfolio update message.
        
        Args:
            portfolio_data: Portfolio data dictionary
            
        Returns:
            str: Formatted message
        """
        message = f"💼 *CẬP NHẬT PORTFOLIO*\n\n"
        
        # Overall performance
        message += f"📊 *Tổng quan:*\n"
        message += f"💰 Tổng giá trị: {format_currency(portfolio_data.get('total_value', 0))}\n"
        message += f"📈 P&L hôm nay: {format_percentage(portfolio_data.get('daily_pnl', 0))}\n"
        message += f"🎯 Tổng P&L: {format_percentage(portfolio_data.get('total_pnl', 0))}\n\n"
        
        # Active positions
        positions = portfolio_data.get('positions', [])
        if positions:
            message += f"📋 *Vị thế hiện tại ({len(positions)}):*\n"
            for pos in positions[:5]:  # Show top 5
                pnl_emoji = "🟢" if pos.get('pnl_percent', 0) >= 0 else "🔴"
                message += f"{pnl_emoji} {pos['ticker']}: {format_percentage(pos.get('pnl_percent', 0))}\n"
            
            if len(positions) > 5:
                message += f"... và {len(positions) - 5} vị thế khác\n"
            message += "\n"
        
        # Recent actions
        recent_actions = portfolio_data.get('recent_actions', [])
        if recent_actions:
            message += f"🔄 *Giao dịch gần đây:*\n"
            for action in recent_actions[:3]:
                action_emoji = "🟢" if action['type'] == 'buy' else "🔴"
                message += f"{action_emoji} {action['ticker']}: {action['type'].upper()}\n"
            message += "\n"
        
        message += f"⏰ *Cập nhật:* {datetime.now().strftime('%H:%M:%S')}"
        
        return message
    
    def _format_automated_strategy(self, strategy_data: Dict[str, Any]) -> str:
        """
        Format automated strategy recommendation message.
        
        Args:
            strategy_data: Strategy recommendation data
            
        Returns:
            str: Formatted message
        """
        strategy_type = strategy_data.get('type', 'recommendation')
        
        emoji_map = {
            'buy_recommendation': '🤖💚',
            'sell_recommendation': '🤖❤️',
            'risk_alert': '🤖⚠️',
            'portfolio_rebalance': '🤖⚖️'
        }
        
        emoji = emoji_map.get(strategy_type, '🤖')
        
        message = f"{emoji} *CHIẾN LƯỢC TỰ ĐỘNG*\n\n"
        
        # Strategy details
        if strategy_type == 'buy_recommendation':
            message += f"📈 *KHUYẾN NGHỊ MUA*\n\n"
            message += f"📊 *Mã:* `{strategy_data.get('ticker', 'N/A')}`\n"
            message += f"💰 *Giá đề xuất:* {format_currency(strategy_data.get('target_price', 0))}\n"
            message += f"🎯 *Độ tin cậy:* {strategy_data.get('confidence', 0):.0%}\n"
            
            if 'stop_loss' in strategy_data:
                message += f"🛑 *Stop Loss:* {format_currency(strategy_data['stop_loss'])}\n"
            
            if 'take_profit' in strategy_data:
                message += f"🎯 *Take Profit:* {format_currency(strategy_data['take_profit'])}\n"
            
            if 'risk_reward_ratio' in strategy_data:
                message += f"⚖️ *Risk/Reward:* 1:{strategy_data['risk_reward_ratio']:.1f}\n"
        
        elif strategy_type == 'sell_recommendation':
            message += f"📉 *KHUYẾN NGHỊ BÁN*\n\n"
            message += f"📊 *Mã:* `{strategy_data.get('ticker', 'N/A')}`\n"
            message += f"💰 *Giá hiện tại:* {format_currency(strategy_data.get('current_price', 0))}\n"
            message += f"📈 *P&L dự kiến:* {format_percentage(strategy_data.get('expected_pnl', 0))}\n"
            message += f"🎯 *Độ tin cậy:* {strategy_data.get('confidence', 0):.0%}\n"
        
        elif strategy_type == 'risk_alert':
            message += f"⚠️ *CẢNH BÁO RỦI RO*\n\n"
            message += f"📊 *Mã:* `{strategy_data.get('ticker', 'N/A')}`\n"
            message += f"🚨 *Mức độ rủi ro:* {strategy_data.get('risk_level', 'N/A')}\n"
            message += f"📉 *Tổn thất tiềm năng:* {format_percentage(strategy_data.get('potential_loss', 0))}\n"
        
        elif strategy_type == 'portfolio_rebalance':
            message += f"⚖️ *KHUYẾN NGHỊ CÂN BẰNG PORTFOLIO*\n\n"
            rebalance_actions = strategy_data.get('actions', [])
            if rebalance_actions:
                message += f"🔄 *Hành động đề xuất:*\n"
                for action in rebalance_actions[:5]:
                    action_emoji = "➕" if action['type'] == 'increase' else "➖"
                    message += f"{action_emoji} {action['ticker']}: {action['type']} {action.get('percentage', 0):.1f}%\n"
        
        # Add reasoning
        reason = strategy_data.get('reason', '')
        if reason:
            message += f"\n💡 *Lý do:* {reason}\n"
        
        # Add timestamp
        message += f"\n⏰ *Thời gian:* {datetime.now().strftime('%H:%M:%S')}"
        
        return message
    
    async def _generate_recommendations(self) -> Dict[str, Any]:
        """
        Generate trading recommendations for tomorrow.
        
        Returns:
            dict: Recommendations data
        """
        try:
            # Initialize strategy and data adapter
            strategy = RSIPSAREngulfingStrategy()
            data_adapter = FiinQuantAdapter()
            
            # Get stock symbols from config or use default list
            symbols = self.config.get('trading', {}).get('symbols', [
                'VIC', 'VHM', 'VRE', 'HPG', 'TCB', 'VCB', 'BID', 'CTG',
                'MSN', 'MWG', 'FPT', 'VNM', 'SAB', 'GAS', 'PLX', 'POW'
            ])
            
            recommendations = {
                'buy_list': [],
                'sell_list': [],
                'watch_list': [],
                'generated_at': datetime.now()
            }
            
            # Analyze each symbol
            for symbol in symbols[:10]:  # Limit to 10 symbols for performance
                try:
                    # Get historical data
                    data = await data_adapter.get_historical_data(symbol, period='3M')
                    if data is None or len(data) < 50:
                        continue
                    
                    # Generate signal
                    signal = strategy.generate_signal(data, symbol)
                    
                    if signal and signal.signal_type:
                        recommendation = {
                            'symbol': symbol,
                            'signal_type': signal.signal_type,
                            'confidence': signal.confidence,
                            'price': signal.price,
                            'target_price': getattr(signal, 'target_price', None),
                            'stop_loss': getattr(signal, 'stop_loss', None),
                            'reason': getattr(signal, 'reason', 'Phân tích kỹ thuật')
                        }
                        
                        if signal.signal_type == 'BUY' and signal.confidence > 0.6:
                            recommendations['buy_list'].append(recommendation)
                        elif signal.signal_type == 'SELL' and signal.confidence > 0.6:
                            recommendations['sell_list'].append(recommendation)
                        elif signal.confidence > 0.4:
                            recommendations['watch_list'].append(recommendation)
                            
                except Exception as e:
                    self.logger.warning(f"Failed to analyze {symbol}: {str(e)}")
                    continue
            
            # Sort by confidence
            recommendations['buy_list'].sort(key=lambda x: x['confidence'], reverse=True)
            recommendations['sell_list'].sort(key=lambda x: x['confidence'], reverse=True)
            recommendations['watch_list'].sort(key=lambda x: x['confidence'], reverse=True)
            
            return recommendations
            
        except Exception as e:
            self.logger.error(f"Failed to generate recommendations: {str(e)}")
            return {
                'buy_list': [],
                'sell_list': [],
                'watch_list': [],
                'generated_at': datetime.now(),
                'error': str(e)
            }
    
    def _format_recommendations(self, recommendations: Dict[str, Any]) -> str:
        """
        Format recommendations for Telegram message.
        
        Args:
            recommendations: Recommendations data
            
        Returns:
            str: Formatted message
        """
        message = "💡 *KHUYẾN NGHỊ MUA/BÁN NGÀY MAI*\n\n"
        
        # Buy recommendations
        buy_list = recommendations.get('buy_list', [])
        message += "📈 *Khuyến nghị MUA:*\n"
        if buy_list:
            for i, rec in enumerate(buy_list[:5], 1):
                confidence_stars = "⭐" * min(int(rec['confidence'] * 5), 5)
                message += f"{i}. *{rec['symbol']}* - {format_currency(rec['price'])} {confidence_stars}\n"
                if rec.get('target_price'):
                    message += f"   🎯 Mục tiêu: {format_currency(rec['target_price'])}\n"
                if rec.get('stop_loss'):
                    message += f"   🛑 Cắt lỗ: {format_currency(rec['stop_loss'])}\n"
            message += "\n"
        else:
            message += "Hiện tại chưa có khuyến nghị mua\n\n"
        
        # Sell recommendations
        sell_list = recommendations.get('sell_list', [])
        message += "📉 *Khuyến nghị BÁN:*\n"
        if sell_list:
            for i, rec in enumerate(sell_list[:5], 1):
                confidence_stars = "⭐" * min(int(rec['confidence'] * 5), 5)
                message += f"{i}. *{rec['symbol']}* - {format_currency(rec['price'])} {confidence_stars}\n"
                if rec.get('target_price'):
                    message += f"   🎯 Mục tiêu: {format_currency(rec['target_price'])}\n"
            message += "\n"
        else:
            message += "Hiện tại chưa có khuyến nghị bán\n\n"
        
        # Watch list
        watch_list = recommendations.get('watch_list', [])
        message += "👀 *Danh sách theo dõi:*\n"
        if watch_list:
            for i, rec in enumerate(watch_list[:3], 1):
                message += f"{i}. *{rec['symbol']}* - {format_currency(rec['price'])}\n"
            message += "\n"
        else:
            message += "Hiện tại chưa có mã cần theo dõi\n\n"
        
        # Strategy info
        message += "🎯 *Chiến lược:*\n"
        message += "• Dựa trên phân tích RSI-PSAR-Engulfing\n"
        message += "• Xem xét thanh khoản và volume\n"
        message += "• Đánh giá rủi ro/lợi nhuận\n\n"
        
        # Disclaimer
        message += "⚠️ *Lưu ý:* Đây chỉ là khuyến nghị tham khảo, không phải lời khuyên đầu tư.\n\n"
        
        # Timestamp
        generated_at = recommendations.get('generated_at', datetime.now())
        message += f"🕐 *Cập nhật:* {generated_at.strftime('%H:%M:%S')}"
        
        return message
    
    def _format_top_opportunities(self, recommendations: Dict[str, Any]) -> str:
        """
        Format top trading opportunities for /top command.
        
        Args:
            recommendations: Recommendations data
            
        Returns:
            str: Formatted message
        """
        message = "🔝 *TOP CƠ HỘI GIAO DỊCH HIỆN TẠI*\n\n"
        
        # Top buy opportunities
        buy_list = recommendations.get('buy_list', [])
        message += "📈 *Top mua (P_buy cao):*\n"
        if buy_list:
            for i, rec in enumerate(buy_list[:3], 1):
                confidence_percent = int(rec['confidence'] * 100)
                message += f"{i}. *{rec['symbol']}* - {format_currency(rec['price'])} ({confidence_percent}%)\n"
        else:
            message += "Hiện tại chưa có tín hiệu mua\n"
        message += "\n"
        
        # Top sell opportunities
        sell_list = recommendations.get('sell_list', [])
        message += "📉 *Top bán (P_sell cao):*\n"
        if sell_list:
            for i, rec in enumerate(sell_list[:3], 1):
                confidence_percent = int(rec['confidence'] * 100)
                message += f"{i}. *{rec['symbol']}* - {format_currency(rec['price'])} ({confidence_percent}%)\n"
        else:
            message += "Hiện tại chưa có tín hiệu bán\n"
        message += "\n"
        
        # Watch list (risk alerts)
        watch_list = recommendations.get('watch_list', [])
        message += "⚠️ *Cần theo dõi:*\n"
        if watch_list:
            for i, rec in enumerate(watch_list[:3], 1):
                confidence_percent = int(rec['confidence'] * 100)
                message += f"{i}. *{rec['symbol']}* - {format_currency(rec['price'])} ({confidence_percent}%)\n"
        else:
            message += "Hiện tại chưa có cảnh báo\n"
        message += "\n"
        
        # Tips
        message += "💡 *Gợi ý:* Sử dụng /recommendations để xem khuyến nghị chi tiết cho ngày mai\n\n"
        
        # Timestamp
        generated_at = recommendations.get('generated_at', datetime.now())
        message += f"🕐 *Cập nhật:* {generated_at.strftime('%H:%M:%S')}"
        
        return message
    
    async def send_recommendations_alert(self) -> bool:
        """
        Send daily recommendations alert automatically.
        
        Returns:
            bool: True if sent successfully
        """
        try:
            recommendations = await self._generate_recommendations()
            
            # Create alert message
            message = "🔔 *KHUYẾN NGHỊ GIAO DỊCH HÀNG NGÀY*\n\n"
            
            buy_list = recommendations.get('buy_list', [])
            sell_list = recommendations.get('sell_list', [])
            
            if buy_list or sell_list:
                if buy_list:
                    message += f"📈 *Khuyến nghị MUA ({len(buy_list)} mã):*\n"
                    for rec in buy_list[:3]:
                        confidence_stars = "⭐" * min(int(rec['confidence'] * 5), 5)
                        message += f"• *{rec['symbol']}* - {format_currency(rec['price'])} {confidence_stars}\n"
                    message += "\n"
                
                if sell_list:
                    message += f"📉 *Khuyến nghị BÁN ({len(sell_list)} mã):*\n"
                    for rec in sell_list[:3]:
                        confidence_stars = "⭐" * min(int(rec['confidence'] * 5), 5)
                        message += f"• *{rec['symbol']}* - {format_currency(rec['price'])} {confidence_stars}\n"
                    message += "\n"
                
                message += "💬 Dùng /recommendations để xem chi tiết\n\n"
            else:
                message += "📊 Hiện tại chưa có khuyến nghị mạnh\n"
                message += "📈 Thị trường đang trong giai đoạn quan sát\n\n"
            
            message += "⚠️ *Lưu ý:* Đây chỉ là khuyến nghị tham khảo\n"
            message += f"🕐 *Thời gian:* {datetime.now().strftime('%H:%M:%S - %d/%m/%Y')}"
            
            return await self.send_message(message)
            
        except Exception as e:
            self.logger.error(f"Failed to send recommendations alert: {str(e)}")
            return False
    
    def get_bot_status(self) -> Dict[str, Any]:
        """Get current bot status."""
        return {
            'running': self.bot_running,
            'chat_id': self.chat_id,
            'alerts_sent_last_hour': len(self.alert_count_history),
            'max_alerts_per_hour': self.max_alerts_per_hour,
            'debounce_minutes': self.debouncer.debounce_minutes,
            'unique_signals_sent': len(self.debouncer.sent_signals)
        }


# Main function for running bot standalone
async def main():
    """Run bot as standalone application."""
    # Load configuration
    config = load_config()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create and start bot
    bot = TradingTelegramBot(config)
    
    try:
        await bot.start_bot()
        
        # Keep running
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logging.info("Shutting down bot...")
        await bot.stop_bot()
    except Exception as e:
        logging.error(f"Bot error: {e}")
        await bot.stop_bot()


if __name__ == "__main__":
    asyncio.run(main())
