"""
FiinQuant Adapter for Realtime Trading Data
Handles authentication, data fetching, caching, and retry logic.
"""

import time
import logging
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timedelta
import pandas as pd
import asyncio
from threading import Thread, Event
import json
import os
from dataclasses import dataclass

# FiinQuantX - Real FiinQuant integration (REQUIRED)
try:
    from FiinQuantX import FiinSession, RealTimeData
    FIINQUANT_AVAILABLE = True
except ImportError:
    FIINQUANT_AVAILABLE = False
    raise ImportError(
        "FiinQuantX is required for this system. Please install it from FiinQuant. "
        "Contact FiinQuant support to get the FiinQuantX package and premium account access."
    )


@dataclass
class MarketDataPoint:
    """Standardized market data structure."""
    ticker: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    change: float
    change_percent: float
    total_match_value: float = 0.0
    foreign_buy_volume: int = 0
    foreign_sell_volume: int = 0
    match_volume: int = 0


class FiinQuantAdapter:
    """
    FiinQuant API adapter with session management, caching, and retry logic.
    """
    
    def __init__(self, username: str, password: str, 
                 retry_attempts: int = 3, retry_delay: int = 5,
                 cache_duration: int = 300):
        """
        Initialize FiinQuant adapter.
        
        Args:
            username: FiinQuant username
            password: FiinQuant password  
            retry_attempts: Number of retry attempts for failed requests
            retry_delay: Delay between retries (seconds)
            cache_duration: Cache duration for session (seconds)
        """
        self.username = username
        self.password = password
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        self.cache_duration = cache_duration
        
        self.client = None
        self.session_created_at = None
        self.is_logged_in = False
        
        # Realtime streaming
        self.stream_active = False
        self.stream_thread = None
        self.stream_stop_event = Event()
        self.stream_callbacks: Dict[str, List[Callable]] = {}
        
        # Data cache
        self.data_cache: Dict[str, Dict] = {}
        self.cache_timestamps: Dict[str, datetime] = {}
        
        self.logger = logging.getLogger(__name__)
        
        if not FIINQUANT_AVAILABLE:
            self.logger.error("FiinQuantX not available. Please install it.")
    
    def _is_session_valid(self) -> bool:
        """Check if current session is still valid."""
        if not self.is_logged_in or not self.session_created_at:
            return False
            
        elapsed = datetime.now() - self.session_created_at
        return elapsed.total_seconds() < self.cache_duration
    
    def login(self) -> bool:
        """
        Login to FiinQuant with retry logic.
        
        Returns:
            bool: Success status
        """
        if not FIINQUANT_AVAILABLE:
            self.logger.error("FiinQuantX not available")
            return False
            
        if self._is_session_valid():
            self.logger.info("Using existing valid session")
            return True
        
        for attempt in range(self.retry_attempts):
            try:
                self.logger.info(f"Attempting to login to FiinQuant (attempt {attempt + 1})")
                
                self.client = FiinSession(
                    username=self.username,
                    password=self.password
                ).login()
                
                self.session_created_at = datetime.now()
                self.is_logged_in = True
                
                self.logger.info("Successfully logged in to FiinQuant")
                return True
                
            except Exception as e:
                self.logger.error(f"Login attempt {attempt + 1} failed: {str(e)}")
                if attempt < self.retry_attempts - 1:
                    time.sleep(self.retry_delay)
                else:
                    self.logger.error("All login attempts failed")
                    
        self.is_logged_in = False
        return False
    
    def fetch_historical_data(self, tickers: List[str], 
                            timeframe: str = "15m",
                            period: int = 100,
                            from_date: Optional[str] = None,
                            to_date: Optional[str] = None,
                            fields: Optional[List[str]] = None) -> pd.DataFrame:
        """
        Fetch historical OHLCV data.
        
        Args:
            tickers: List of stock symbols
            timeframe: Time frame (1m, 5m, 15m, 30m, 1h, 1d)
            period: Number of periods (if not using date range)
            from_date: Start date (YYYY-MM-DD format)
            to_date: End date (YYYY-MM-DD format)  
            fields: Data fields to fetch
            
        Returns:
            pd.DataFrame: Historical data
        """
        if not self.login():
            raise Exception("Failed to login to FiinQuant")
        
        if fields is None:
            fields = ['open', 'high', 'low', 'close', 'volume']
        
        try:
            # Use date range if provided, otherwise use period
            if from_date and to_date:
                data = self.client.Fetch_Trading_Data(
                    realtime=False,
                    tickers=tickers,
                    fields=fields,
                    adjusted=True,
                    by=timeframe,
                    from_date=from_date,
                    to_date=to_date
                ).get_data()
            else:
                data = self.client.Fetch_Trading_Data(
                    realtime=False,
                    tickers=tickers,
                    fields=fields,
                    adjusted=True,
                    by=timeframe,
                    period=period
                ).get_data()
            
            self.logger.info(f"Successfully fetched historical data for {len(tickers)} symbols")
            return data
            
        except Exception as e:
            self.logger.error(f"Failed to fetch historical data: {str(e)}")
            raise
    
    def start_realtime_stream(self, tickers: List[str], 
                            callback: Callable[[MarketDataPoint], None]) -> bool:
        """
        Start realtime data streaming.
        
        Args:
            tickers: List of stock symbols to monitor
            callback: Function to process each data point
            
        Returns:
            bool: Success status
        """
        if not self.login():
            self.logger.error("Failed to login for realtime stream")
            return False
        
        if self.stream_active:
            self.logger.warning("Stream already active")
            return True
        
        try:
            # Internal callback to process FiinQuant data
            def _process_fiinquant_data(data: 'RealTimeData'):
                try:
                    # Convert FiinQuant data to our standard format
                    market_data = MarketDataPoint(
                        ticker=data.Ticker,
                        timestamp=datetime.now(),  # FiinQuant may not provide exact timestamp
                        open=getattr(data, 'Open', 0.0),
                        high=getattr(data, 'High', 0.0),
                        low=getattr(data, 'Low', 0.0),
                        close=getattr(data, 'Close', 0.0),
                        volume=getattr(data, 'TotalMatchVolume', 0),
                        change=getattr(data, 'Change', 0.0),
                        change_percent=getattr(data, 'ChangePercent', 0.0),
                        total_match_value=getattr(data, 'TotalMatchValue', 0.0),
                        foreign_buy_volume=getattr(data, 'ForeignBuyVolumeTotal', 0),
                        foreign_sell_volume=getattr(data, 'ForeignSellVolumeTotal', 0),
                        match_volume=getattr(data, 'MatchVolume', 0)
                    )
                    
                    # Call user callback
                    callback(market_data)
                    
                except Exception as e:
                    self.logger.error(f"Error processing realtime data: {str(e)}")
            
            # Start FiinQuant stream
            self.stream_events = self.client.Trading_Data_Stream(
                tickers=tickers,
                callback=_process_fiinquant_data
            )
            
            # Run in separate thread
            def _run_stream():
                try:
                    self.stream_events.start()
                    while not self.stream_stop_event.is_set():
                        time.sleep(0.1)
                    self.stream_events.stop()
                except Exception as e:
                    self.logger.error(f"Stream error: {str(e)}")
                    self.stream_active = False
            
            self.stream_thread = Thread(target=_run_stream, daemon=True)
            self.stream_thread.start()
            
            self.stream_active = True
            self.logger.info(f"Started realtime stream for {len(tickers)} symbols")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start realtime stream: {str(e)}")
            return False
    
    def stop_realtime_stream(self):
        """Stop realtime data streaming."""
        if not self.stream_active:
            return
        
        self.logger.info("Stopping realtime stream...")
        self.stream_stop_event.set()
        
        if self.stream_thread and self.stream_thread.is_alive():
            self.stream_thread.join(timeout=10)
        
        self.stream_active = False
        self.logger.info("Realtime stream stopped")
    
    def get_latest_data(self, ticker: str, use_cache: bool = True) -> Optional[MarketDataPoint]:
        """
        Get latest data point for a ticker.
        
        Args:
            ticker: Stock symbol
            use_cache: Whether to use cached data
            
        Returns:
            MarketDataPoint: Latest data or None
        """
        cache_key = f"latest_{ticker}"
        
        # Check cache first
        if use_cache and cache_key in self.data_cache:
            cache_time = self.cache_timestamps.get(cache_key, datetime.min)
            if (datetime.now() - cache_time).total_seconds() < 60:  # 1-minute cache
                return self.data_cache[cache_key]
        
        try:
            # Fetch single period data
            df = self.fetch_historical_data([ticker], period=1)
            
            if df.empty:
                return None
            
            # Convert to MarketDataPoint
            row = df.iloc[-1]  # Latest row
            market_data = MarketDataPoint(
                ticker=ticker,
                timestamp=datetime.now(),
                open=row.get('open', 0.0),
                high=row.get('high', 0.0),
                low=row.get('low', 0.0),
                close=row.get('close', 0.0),
                volume=row.get('volume', 0),
                change=0.0,  # Calculate if reference available
                change_percent=0.0
            )
            
            # Cache the result
            self.data_cache[cache_key] = market_data
            self.cache_timestamps[cache_key] = datetime.now()
            
            return market_data
            
        except Exception as e:
            self.logger.error(f"Failed to get latest data for {ticker}: {str(e)}")
            return None
    
    def is_market_open(self) -> bool:
        """
        Check if market is currently open.
        
        Returns:
            bool: True if market is open
        """
        now = datetime.now()
        
        # Vietnam market hours: 9:00 - 15:00, Monday-Friday
        if now.weekday() >= 5:  # Weekend
            return False
        
        market_open = now.replace(hour=9, minute=0, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=0, second=0, microsecond=0)
        
        return market_open <= now <= market_close
    
    def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on the adapter.
        
        Returns:
            Dict: Health status information
        """
        status = {
            "fiinquant_available": FIINQUANT_AVAILABLE,
            "logged_in": self.is_logged_in,
            "session_valid": self._is_session_valid(),
            "stream_active": self.stream_active,
            "market_open": self.is_market_open(),
            "cache_size": len(self.data_cache),
            "last_login": self.session_created_at.isoformat() if self.session_created_at else None
        }
        
        return status
    
    def __del__(self):
        """Cleanup on object destruction."""
        if self.stream_active:
            self.stop_realtime_stream()


