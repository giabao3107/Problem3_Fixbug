"""
Database Manager for Trading System
Handles SQLite database operations for signals, trades, and market data.
"""

import sqlite3
import aiosqlite
import pandas as pd
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import json

from strategy.rsi_psar_engulfing import TradingSignal, StrategyState


class DatabaseManager:
    """
    Manages SQLite database for trading system data.
    Handles signals, trades, market data, and performance tracking.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize database manager.
        
        Args:
            config: System configuration
        """
        self.config = config
        self.db_path = config.get('database', {}).get('path', 'database/trading_data.db')
        
        # Ensure database directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        self.connection = None
        self.logger = logging.getLogger(__name__)
    
    async def initialize(self):
        """Initialize database and create tables."""
        try:
            self.connection = await aiosqlite.connect(self.db_path)
            await self._create_tables()
            self.logger.info(f"Database initialized: {self.db_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize database: {str(e)}")
            raise
    
    async def _create_tables(self):
        """Create database tables if they don't exist."""
        
        # Signals table
        await self.connection.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                ticker TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                confidence REAL NOT NULL,
                entry_price REAL NOT NULL,
                stop_loss REAL,
                take_profit REAL,
                reason TEXT,
                metadata TEXT,
                timeframe TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes for signals table
        await self.connection.execute("CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp)")
        await self.connection.execute("CREATE INDEX IF NOT EXISTS idx_signals_ticker ON signals(ticker)")
        await self.connection.execute("CREATE INDEX IF NOT EXISTS idx_signals_signal_type ON signals(signal_type)")
        
        # Market data table  
        await self.connection.execute("""
            CREATE TABLE IF NOT EXISTS market_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                ticker TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                open_price REAL NOT NULL,
                high_price REAL NOT NULL,
                low_price REAL NOT NULL,
                close_price REAL NOT NULL,
                volume INTEGER NOT NULL,
                rsi REAL,
                psar REAL,
                engulfing_signal INTEGER,
                volume_anomaly INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(timestamp, ticker, timeframe)
            )
        """)
        
        # Create indexes for market_data table
        await self.connection.execute("CREATE INDEX IF NOT EXISTS idx_market_data_timestamp ON market_data(timestamp)")
        await self.connection.execute("CREATE INDEX IF NOT EXISTS idx_market_data_ticker ON market_data(ticker)")
        await self.connection.execute("CREATE INDEX IF NOT EXISTS idx_market_data_timeframe ON market_data(timeframe)")
        
        # Trades table
        await self.connection.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                entry_date DATETIME NOT NULL,
                exit_date DATETIME,
                entry_price REAL NOT NULL,
                exit_price REAL,
                quantity INTEGER NOT NULL,
                trade_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                pnl_amount REAL,
                pnl_percent REAL,
                max_price_reached REAL,
                min_price_reached REAL,
                stop_loss_price REAL,
                take_profit_price REAL,
                exit_reason TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes for trades table
        await self.connection.execute("CREATE INDEX IF NOT EXISTS idx_trades_ticker ON trades(ticker)")
        await self.connection.execute("CREATE INDEX IF NOT EXISTS idx_trades_entry_date ON trades(entry_date)")
        await self.connection.execute("CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status)")
        
        # Performance metrics table
        await self.connection.execute("""
            CREATE TABLE IF NOT EXISTS performance_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL UNIQUE,
                total_signals INTEGER DEFAULT 0,
                buy_signals INTEGER DEFAULT 0,
                sell_signals INTEGER DEFAULT 0,
                risk_warnings INTEGER DEFAULT 0,
                trades_opened INTEGER DEFAULT 0,
                trades_closed INTEGER DEFAULT 0,
                total_pnl REAL DEFAULT 0,
                win_rate REAL,
                avg_trade_duration REAL,
                max_drawdown REAL,
                portfolio_value REAL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # System logs table
        await self.connection.execute("""
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                level TEXT NOT NULL,
                component TEXT NOT NULL,
                message TEXT NOT NULL,
                details TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes for system_logs table
        await self.connection.execute("CREATE INDEX IF NOT EXISTS idx_system_logs_timestamp ON system_logs(timestamp)")
        await self.connection.execute("CREATE INDEX IF NOT EXISTS idx_system_logs_level ON system_logs(level)")
        await self.connection.execute("CREATE INDEX IF NOT EXISTS idx_system_logs_component ON system_logs(component)")
        
        await self.connection.commit()
        self.logger.info("Database tables created/verified")
    
    async def save_signal(self, signal: TradingSignal) -> int:
        """
        Save trading signal to database.
        
        Args:
            signal: TradingSignal object
            
        Returns:
            int: Signal ID
        """
        try:
            cursor = await self.connection.execute("""
                INSERT INTO signals (
                    timestamp, ticker, signal_type, confidence, entry_price,
                    stop_loss, take_profit, reason, metadata, timeframe
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal.timestamp,
                signal.ticker,
                signal.signal_type,
                signal.confidence,
                signal.entry_price,
                signal.stop_loss,
                signal.take_profit,
                signal.reason,
                json.dumps(signal.metadata) if signal.metadata else None,
                '15m'  # Default timeframe
            ))
            
            await self.connection.commit()
            return cursor.lastrowid
            
        except Exception as e:
            self.logger.error(f"Failed to save signal: {str(e)}")
            raise
    
    async def save_market_data(self, ticker: str, df: pd.DataFrame, 
                             timeframe: str = '15m') -> bool:
        """
        Save market data to database.
        
        Args:
            ticker: Stock symbol
            df: DataFrame with OHLCV and indicator data
            timeframe: Data timeframe
            
        Returns:
            bool: Success status
        """
        try:
            # Prepare data for insertion
            data_records = []
            
            for _, row in df.iterrows():
                record = (
                    row.get('timestamp', datetime.now()),
                    ticker,
                    timeframe,
                    row.get('open', 0),
                    row.get('high', 0),
                    row.get('low', 0),
                    row.get('close', 0),
                    row.get('volume', 0),
                    row.get('rsi', None),
                    row.get('psar', None),
                    row.get('engulfing_signal', None),
                    row.get('volume_anomaly', None)
                )
                data_records.append(record)
            
            # Bulk insert with conflict resolution
            await self.connection.executemany("""
                INSERT OR REPLACE INTO market_data (
                    timestamp, ticker, timeframe, open_price, high_price,
                    low_price, close_price, volume, rsi, psar,
                    engulfing_signal, volume_anomaly
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, data_records)
            
            await self.connection.commit()
            
            self.logger.debug(f"Saved {len(data_records)} market data records for {ticker}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save market data for {ticker}: {str(e)}")
            return False
    
    async def open_trade(self, ticker: str, entry_price: float, 
                        quantity: int, trade_type: str = 'long',
                        stop_loss: Optional[float] = None,
                        take_profit: Optional[float] = None) -> int:
        """
        Record a new trade opening.
        
        Args:
            ticker: Stock symbol
            entry_price: Entry price
            quantity: Number of shares
            trade_type: 'long' or 'short'
            stop_loss: Stop loss price
            take_profit: Take profit price
            
        Returns:
            int: Trade ID
        """
        try:
            cursor = await self.connection.execute("""
                INSERT INTO trades (
                    ticker, entry_date, entry_price, quantity, trade_type,
                    status, stop_loss_price, take_profit_price,
                    max_price_reached, min_price_reached
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ticker,
                datetime.now(),
                entry_price,
                quantity,
                trade_type,
                'open',
                stop_loss,
                take_profit,
                entry_price,  # Initial max price
                entry_price   # Initial min price
            ))
            
            await self.connection.commit()
            trade_id = cursor.lastrowid
            
            self.logger.info(f"Opened trade {trade_id}: {trade_type} {quantity} {ticker} @ {entry_price}")
            return trade_id
            
        except Exception as e:
            self.logger.error(f"Failed to open trade: {str(e)}")
            raise
    
    async def close_trade(self, trade_id: int, exit_price: float,
                         exit_reason: str = 'manual') -> bool:
        """
        Close an existing trade.
        
        Args:
            trade_id: Trade ID
            exit_price: Exit price
            exit_reason: Reason for closing
            
        Returns:
            bool: Success status
        """
        try:
            # Get trade details first
            cursor = await self.connection.execute(
                "SELECT * FROM trades WHERE id = ? AND status = 'open'", 
                (trade_id,)
            )
            trade = await cursor.fetchone()
            
            if not trade:
                self.logger.warning(f"Trade {trade_id} not found or already closed")
                return False
            
            # Calculate P&L
            entry_price = trade[4]  # entry_price column
            quantity = trade[5]     # quantity column
            
            pnl_amount = (exit_price - entry_price) * quantity
            pnl_percent = (exit_price - entry_price) / entry_price
            
            # Update trade
            await self.connection.execute("""
                UPDATE trades SET
                    exit_date = ?,
                    exit_price = ?,
                    status = 'closed',
                    pnl_amount = ?,
                    pnl_percent = ?,
                    exit_reason = ?
                WHERE id = ?
            """, (
                datetime.now(),
                exit_price,
                pnl_amount,
                pnl_percent,
                exit_reason,
                trade_id
            ))
            
            await self.connection.commit()
            
            self.logger.info(
                f"Closed trade {trade_id}: P&L = {pnl_amount:.0f} ({pnl_percent:.2%}) "
                f"Reason: {exit_reason}"
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to close trade {trade_id}: {str(e)}")
            return False
    
    async def update_trade_prices(self, trade_id: int, current_price: float) -> bool:
        """
        Update max/min prices reached for an open trade.
        
        Args:
            trade_id: Trade ID
            current_price: Current market price
            
        Returns:
            bool: Success status
        """
        try:
            await self.connection.execute("""
                UPDATE trades SET
                    max_price_reached = MAX(max_price_reached, ?),
                    min_price_reached = MIN(min_price_reached, ?)
                WHERE id = ? AND status = 'open'
            """, (current_price, current_price, trade_id))
            
            await self.connection.commit()
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update trade prices: {str(e)}")
            return False
    
    async def get_signals(self, ticker: Optional[str] = None,
                         signal_type: Optional[str] = None,
                         hours: int = 24,
                         limit: int = 100) -> pd.DataFrame:
        """
        Get recent signals from database.
        
        Args:
            ticker: Filter by ticker (optional)
            signal_type: Filter by signal type (optional)
            hours: Hours to look back
            limit: Maximum number of records
            
        Returns:
            pd.DataFrame: Signals data
        """
        try:
            query = """
                SELECT * FROM signals 
                WHERE timestamp > ?
            """
            params = [datetime.now() - timedelta(hours=hours)]
            
            if ticker:
                query += " AND ticker = ?"
                params.append(ticker)
            
            if signal_type:
                query += " AND signal_type = ?"
                params.append(signal_type)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            df = pd.read_sql_query(query, await self.connection, params=params)
            return df
            
        except Exception as e:
            self.logger.error(f"Failed to get signals: {str(e)}")
            return pd.DataFrame()
    
    async def get_open_trades(self, ticker: Optional[str] = None) -> pd.DataFrame:
        """
        Get open trades.
        
        Args:
            ticker: Filter by ticker (optional)
            
        Returns:
            pd.DataFrame: Open trades
        """
        try:
            query = "SELECT * FROM trades WHERE status = 'open'"
            params = []
            
            if ticker:
                query += " AND ticker = ?"
                params.append(ticker)
            
            query += " ORDER BY entry_date DESC"
            
            cursor = await self.connection.execute(query, params)
            rows = await cursor.fetchall()
            
            if not rows:
                return pd.DataFrame()
            
            # Convert to DataFrame
            columns = [description[0] for description in cursor.description]
            df = pd.DataFrame(rows, columns=columns)
            
            return df
            
        except Exception as e:
            self.logger.error(f"Failed to get open trades: {str(e)}")
            return pd.DataFrame()
    
    async def get_market_data(self, ticker: str, timeframe: str = '15m',
                            hours: int = 24) -> pd.DataFrame:
        """
        Get market data from database.
        
        Args:
            ticker: Stock symbol
            timeframe: Data timeframe
            hours: Hours to look back
            
        Returns:
            pd.DataFrame: Market data
        """
        try:
            query = """
                SELECT * FROM market_data 
                WHERE ticker = ? AND timeframe = ? AND timestamp > ?
                ORDER BY timestamp ASC
            """
            
            cutoff_time = datetime.now() - timedelta(hours=hours)
            params = [ticker, timeframe, cutoff_time]
            
            df = pd.read_sql_query(query, await self.connection, params=params)
            return df
            
        except Exception as e:
            self.logger.error(f"Failed to get market data for {ticker}: {str(e)}")
            return pd.DataFrame()
    
    async def update_daily_performance(self, date: datetime.date,
                                     metrics: Dict[str, Any]) -> bool:
        """
        Update daily performance metrics.
        
        Args:
            date: Date for metrics
            metrics: Performance metrics dictionary
            
        Returns:
            bool: Success status
        """
        try:
            await self.connection.execute("""
                INSERT OR REPLACE INTO performance_metrics (
                    date, total_signals, buy_signals, sell_signals, risk_warnings,
                    trades_opened, trades_closed, total_pnl, win_rate,
                    avg_trade_duration, max_drawdown, portfolio_value
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                date,
                metrics.get('total_signals', 0),
                metrics.get('buy_signals', 0),
                metrics.get('sell_signals', 0),
                metrics.get('risk_warnings', 0),
                metrics.get('trades_opened', 0),
                metrics.get('trades_closed', 0),
                metrics.get('total_pnl', 0),
                metrics.get('win_rate', None),
                metrics.get('avg_trade_duration', None),
                metrics.get('max_drawdown', None),
                metrics.get('portfolio_value', None)
            ))
            
            await self.connection.commit()
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update daily performance: {str(e)}")
            return False
    
    async def log_system_event(self, level: str, component: str, 
                              message: str, details: Optional[str] = None) -> bool:
        """
        Log system event to database.
        
        Args:
            level: Log level (INFO, WARNING, ERROR, etc.)
            component: Component name
            message: Log message
            details: Additional details
            
        Returns:
            bool: Success status
        """
        try:
            await self.connection.execute("""
                INSERT INTO system_logs (timestamp, level, component, message, details)
                VALUES (?, ?, ?, ?, ?)
            """, (datetime.now(), level, component, message, details))
            
            await self.connection.commit()
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to log system event: {str(e)}")
            return False
    
    async def cleanup_old_data(self, days: int = 30) -> bool:
        """
        Clean up old data from database.
        
        Args:
            days: Keep data for this many days
            
        Returns:
            bool: Success status
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            # Clean old market data
            await self.connection.execute(
                "DELETE FROM market_data WHERE timestamp < ?", 
                (cutoff_date,)
            )
            
            # Clean old system logs
            await self.connection.execute(
                "DELETE FROM system_logs WHERE timestamp < ?", 
                (cutoff_date,)
            )
            
            # Clean old signals (keep longer)
            signal_cutoff = datetime.now() - timedelta(days=days * 2)
            await self.connection.execute(
                "DELETE FROM signals WHERE timestamp < ?", 
                (signal_cutoff,)
            )
            
            await self.connection.commit()
            
            self.logger.info(f"Cleaned up data older than {days} days")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup old data: {str(e)}")
            return False
    
    async def get_performance_summary(self, days: int = 30) -> Dict[str, Any]:
        """
        Get performance summary for last N days.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Dict: Performance summary
        """
        try:
            cutoff_date = datetime.now().date() - timedelta(days=days)
            
            # Get performance metrics
            cursor = await self.connection.execute("""
                SELECT 
                    SUM(total_signals) as total_signals,
                    SUM(buy_signals) as total_buy,
                    SUM(sell_signals) as total_sell,
                    SUM(risk_warnings) as total_warnings,
                    SUM(trades_opened) as total_opened,
                    SUM(trades_closed) as total_closed,
                    SUM(total_pnl) as total_pnl,
                    AVG(win_rate) as avg_win_rate,
                    MAX(max_drawdown) as max_drawdown
                FROM performance_metrics 
                WHERE date > ?
            """, (cutoff_date,))
            
            metrics = await cursor.fetchone()
            
            # Get trade statistics
            cursor = await self.connection.execute("""
                SELECT 
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN pnl_amount > 0 THEN 1 ELSE 0 END) as winning_trades,
                    AVG(pnl_percent) as avg_pnl_percent,
                    MAX(pnl_percent) as best_trade,
                    MIN(pnl_percent) as worst_trade
                FROM trades 
                WHERE entry_date > ? AND status = 'closed'
            """, (cutoff_date,))
            
            trades = await cursor.fetchone()
            
            summary = {
                'period_days': days,
                'total_signals': metrics[0] or 0,
                'buy_signals': metrics[1] or 0,
                'sell_signals': metrics[2] or 0,
                'risk_warnings': metrics[3] or 0,
                'total_trades': trades[0] or 0,
                'winning_trades': trades[1] or 0,
                'win_rate': trades[1] / trades[0] if trades[0] else 0,
                'avg_pnl_percent': trades[2] or 0,
                'best_trade_percent': trades[3] or 0,
                'worst_trade_percent': trades[4] or 0,
                'total_pnl': metrics[6] or 0,
                'max_drawdown': metrics[8] or 0
            }
            
            return summary
            
        except Exception as e:
            self.logger.error(f"Failed to get performance summary: {str(e)}")
            return {}
    
    async def close(self):
        """Close database connection."""
        if self.connection:
            await self.connection.close()
            self.logger.info("Database connection closed")
