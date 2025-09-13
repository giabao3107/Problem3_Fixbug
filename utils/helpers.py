"""
Helper functions for realtime alert system.
Contains utilities for data processing, formatting, validation, etc.
"""

import os
import json
import yaml
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union
import pandas as pd
import numpy as np
import pytz
import logging
from pathlib import Path
from dotenv import load_dotenv

# Auto-load .env file when this module is imported
load_dotenv()


def load_config(config_path: str = "config/config.yaml") -> Dict[str, Any]:
    """
    Load configuration from YAML file.
    
    Args:
        config_path: Path to config file
        
    Returns:
        Dict: Configuration dictionary
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config
    except FileNotFoundError:
        logging.error(f"Config file not found: {config_path}")
        return {}
    except yaml.YAMLError as e:
        logging.error(f"Error parsing YAML config: {e}")
        return {}


def load_symbols(symbols_path: str = "config/symbols.json") -> Dict[str, Any]:
    """
    Load trading symbols from JSON file.
    
    Args:
        symbols_path: Path to symbols file
        
    Returns:
        Dict: Symbols configuration with all symbols from all exchanges if configured
    """
    try:
        with open(symbols_path, 'r', encoding='utf-8') as f:
            symbols = json.load(f)
            
        # Check if all_exchanges flag is set
        if symbols.get('universe', {}).get('all_exchanges', False):
            try:
                # Try to import vnstock to get all symbols
                from vnstock.api.listing import Listing
                
                # Get all symbols from all exchanges
                lst = Listing(source="vci", random_agent=False, show_log=False)
                all_symbols_df = lst.all_symbols(to_df=True)
                
                # Get symbols by exchange
                exchange_symbols_df = lst.symbols_by_exchange(lang="en")
                
                # Extract symbols by exchange
                hose_symbols = exchange_symbols_df[exchange_symbols_df['exchange'] == 'HOSE']['symbol'].tolist()
                hnx_symbols = exchange_symbols_df[exchange_symbols_df['exchange'] == 'HNX']['symbol'].tolist()
                upcom_symbols = exchange_symbols_df[exchange_symbols_df['exchange'] == 'UPCOM']['symbol'].tolist()
                
                # Update the symbols dictionary
                symbols['universe']['hose_all'] = hose_symbols
                symbols['universe']['hnx_all'] = hnx_symbols
                symbols['universe']['upcom_all'] = upcom_symbols
                
                # Create a combined list of all symbols
                all_symbols = hose_symbols + hnx_symbols + upcom_symbols
                symbols['universe']['all_exchanges_list'] = all_symbols
                
                logging.info(f"Loaded all symbols: HOSE={len(hose_symbols)}, HNX={len(hnx_symbols)}, UPCOM={len(upcom_symbols)}")
            except ImportError:
                logging.warning("vnstock library not available. Using predefined symbols.")
            except Exception as e:
                logging.error(f"Error loading symbols from vnstock: {e}")
                
        return symbols
    except FileNotFoundError:
        logging.error(f"Symbols file not found: {symbols_path}")
        return {"universe": {"vn30": []}}
    except json.JSONDecodeError as e:
        logging.error(f"Error parsing JSON symbols file: {e}")
        return {"universe": {"vn30": []}}


def get_env_variable(key: str, default: Any = None, required: bool = False) -> Any:
    """
    Get environment variable with optional default and validation.
    
    Args:
        key: Environment variable name
        default: Default value if not found
        required: Whether the variable is required
        
    Returns:
        Any: Environment variable value
        
    Raises:
        ValueError: If required variable is missing
    """
    value = os.getenv(key, default)
    
    if required and value is None:
        raise ValueError(f"Required environment variable '{key}' not found")
    
    return value


def setup_logging(config: Dict[str, Any]) -> logging.Logger:
    """
    Setup logging configuration.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        logging.Logger: Configured logger
    """
    log_config = config.get('logging', {})
    
    # Create log directory if it doesn't exist
    log_files = log_config.get('files', {})
    for log_file in log_files.values():
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, log_config.get('level', 'INFO')),
        format=log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'),
        handlers=[
            logging.FileHandler(log_files.get('main', 'log/main.log')),
            logging.StreamHandler()
        ]
    )
    
    logger = logging.getLogger('realtime_alert')
    return logger


def get_vietnam_timezone() -> pytz.timezone:
    """Get Vietnam timezone object."""
    return pytz.timezone('Asia/Ho_Chi_Minh')


def is_trading_hours(config: Dict[str, Any]) -> bool:
    """
    Check if current time is within trading hours.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        bool: True if within trading hours
    """
    market_config = config.get('market', {})
    trading_hours = market_config.get('trading_hours', {})
    
    start_time = trading_hours.get('start', '09:00')
    end_time = trading_hours.get('end', '15:00')
    
    tz = get_vietnam_timezone()
    now = datetime.now(tz)
    
    # Check if weekend
    if now.weekday() >= 5:
        return False
    
    # Parse trading hours
    start_hour, start_minute = map(int, start_time.split(':'))
    end_hour, end_minute = map(int, end_time.split(':'))
    
    start = now.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
    end = now.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
    
    return start <= now <= end


def format_currency(amount: float, currency: str = 'VND') -> str:
    """
    Format currency amount with proper separators.
    
    Args:
        amount: Amount to format
        currency: Currency code
        
    Returns:
        str: Formatted currency string
    """
    if currency == 'VND':
        return f"{amount:,.0f} ₫"
    else:
        return f"{amount:,.2f} {currency}"


def format_percentage(value: float, decimals: int = 2) -> str:
    """
    Format percentage with proper sign and decimals.
    
    Args:
        value: Percentage value (0.15 for 15%)
        decimals: Number of decimal places
        
    Returns:
        str: Formatted percentage string
    """
    return f"{value*100:+.{decimals}f}%"


def calculate_position_size(portfolio_value: float, risk_percent: float, 
                          entry_price: float, stop_loss_price: float) -> int:
    """
    Calculate position size based on risk management rules.
    
    Args:
        portfolio_value: Total portfolio value
        risk_percent: Risk percentage (0.02 for 2%)
        entry_price: Entry price per share
        stop_loss_price: Stop loss price per share
        
    Returns:
        int: Number of shares to buy
    """
    if entry_price <= 0 or stop_loss_price <= 0:
        return 0
    
    # Calculate risk amount in currency
    risk_amount = portfolio_value * risk_percent
    
    # Calculate risk per share
    risk_per_share = abs(entry_price - stop_loss_price)
    
    if risk_per_share <= 0:
        return 0
    
    # Calculate position size
    position_size = int(risk_amount / risk_per_share)
    
    return max(0, position_size)


def validate_ticker(ticker: str) -> bool:
    """
    Validate Vietnamese stock ticker format.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        bool: True if valid ticker format
    """
    if not ticker or not isinstance(ticker, str):
        return False
    
    ticker = ticker.upper().strip()
    
    # Vietnamese stock tickers: 3 letters + optional number
    # Examples: ACB, FPT, VN30F1M, etc.
    if len(ticker) < 3 or len(ticker) > 10:
        return False
    
    # Should start with letters
    if not ticker[:3].isalpha():
        return False
    
    return True


def clean_ticker_list(tickers: List[str]) -> List[str]:
    """
    Clean and validate list of tickers.
    
    Args:
        tickers: List of ticker symbols
        
    Returns:
        List[str]: Cleaned and validated tickers
    """
    cleaned = []
    for ticker in tickers:
        if validate_ticker(ticker):
            cleaned.append(ticker.upper().strip())
    
    return list(set(cleaned))  # Remove duplicates


def calculate_drawdown(prices: pd.Series) -> pd.Series:
    """
    Calculate running maximum drawdown.
    
    Args:
        prices: Price series
        
    Returns:
        pd.Series: Drawdown percentages
    """
    peak = prices.expanding().max()
    drawdown = (prices - peak) / peak
    return drawdown


def detect_outliers(data: pd.Series, method: str = 'iqr', 
                   threshold: float = 1.5) -> pd.Series:
    """
    Detect outliers in data series.
    
    Args:
        data: Data series
        method: Detection method ('iqr' or 'zscore')
        threshold: Threshold for outlier detection
        
    Returns:
        pd.Series: Boolean series indicating outliers
    """
    if method == 'iqr':
        Q1 = data.quantile(0.25)
        Q3 = data.quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - threshold * IQR
        upper_bound = Q3 + threshold * IQR
        return (data < lower_bound) | (data > upper_bound)
    
    elif method == 'zscore':
        z_scores = np.abs((data - data.mean()) / data.std())
        return z_scores > threshold
    
    else:
        raise ValueError("Method must be 'iqr' or 'zscore'")


def resample_data(df: pd.DataFrame, target_frequency: str, 
                  agg_methods: Dict[str, str] = None) -> pd.DataFrame:
    """
    Resample OHLCV data to different timeframe.
    
    Args:
        df: OHLCV DataFrame with datetime index
        target_frequency: Target frequency ('5T', '15T', '1H', etc.)
        agg_methods: Custom aggregation methods for columns
        
    Returns:
        pd.DataFrame: Resampled data
    """
    if agg_methods is None:
        agg_methods = {
            'open': 'first',
            'high': 'max', 
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }
    
    # Ensure datetime index
    if not isinstance(df.index, pd.DatetimeIndex):
        if 'time' in df.columns:
            df = df.set_index('time')
        elif 'timestamp' in df.columns:
            df = df.set_index('timestamp')
        else:
            raise ValueError("DataFrame must have datetime index or 'time'/'timestamp' column")
    
    # Resample data
    resampled = df.resample(target_frequency).agg(agg_methods)
    
    # Remove empty periods
    resampled = resampled.dropna()
    
    return resampled


def save_to_csv(df: pd.DataFrame, filename: str, append: bool = False):
    """
    Save DataFrame to CSV with proper formatting.
    
    Args:
        df: DataFrame to save
        filename: Output filename
        append: Whether to append to existing file
    """
    # Create directory if it doesn't exist
    Path(filename).parent.mkdir(parents=True, exist_ok=True)
    
    mode = 'a' if append else 'w'
    header = not (append and Path(filename).exists())
    
    df.to_csv(filename, mode=mode, header=header, index=True, 
              date_format='%Y-%m-%d %H:%M:%S')


def load_from_csv(filename: str, parse_dates: List[str] = None) -> pd.DataFrame:
    """
    Load DataFrame from CSV with proper parsing.
    
    Args:
        filename: Input filename
        parse_dates: Columns to parse as dates
        
    Returns:
        pd.DataFrame: Loaded data
    """
    if not Path(filename).exists():
        return pd.DataFrame()
    
    if parse_dates is None:
        parse_dates = ['time', 'timestamp']
    
    # Filter parse_dates to only include existing columns
    df = pd.read_csv(filename, index_col=0)
    existing_date_cols = [col for col in parse_dates if col in df.columns]
    
    if existing_date_cols:
        df = pd.read_csv(filename, index_col=0, parse_dates=existing_date_cols)
    
    return df


def rate_limiter(calls_per_second: float = 1.0):
    """
    Decorator for rate limiting function calls.
    
    Args:
        calls_per_second: Maximum calls per second
        
    Returns:
        Decorator function
    """
    import time
    from functools import wraps
    
    min_interval = 1.0 / calls_per_second
    last_called = [0.0]
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            left_to_wait = min_interval - elapsed
            
            if left_to_wait > 0:
                time.sleep(left_to_wait)
            
            ret = func(*args, **kwargs)
            last_called[0] = time.time()
            return ret
        
        return wrapper
    return decorator


class DataCache:
    """Simple in-memory cache with TTL support."""
    
    def __init__(self, default_ttl: int = 300):
        """
        Initialize cache.
        
        Args:
            default_ttl: Default time-to-live in seconds
        """
        self.cache: Dict[str, Dict] = {}
        self.default_ttl = default_ttl
    
    def get(self, key: str) -> Any:
        """Get value from cache if not expired."""
        if key in self.cache:
            item = self.cache[key]
            if datetime.now() < item['expires_at']:
                return item['value']
            else:
                del self.cache[key]
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set value in cache with TTL."""
        if ttl is None:
            ttl = self.default_ttl
        
        self.cache[key] = {
            'value': value,
            'expires_at': datetime.now() + timedelta(seconds=ttl)
        }
    
    def delete(self, key: str):
        """Delete key from cache."""
        if key in self.cache:
            del self.cache[key]
    
    def clear(self):
        """Clear all cache entries."""
        self.cache.clear()
    
    def cleanup(self):
        """Remove expired entries."""
        now = datetime.now()
        expired_keys = [
            key for key, item in self.cache.items()
            if now >= item['expires_at']
        ]
        for key in expired_keys:
            del self.cache[key]


class CircuitBreaker:
    """Circuit breaker for handling system failures."""
    
    def __init__(self, failure_threshold: int = 5, 
                 recovery_timeout: int = 60):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Timeout before attempting recovery
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func, *args, **kwargs):
        """
        Execute function with circuit breaker protection.
        
        Args:
            func: Function to execute
            *args, **kwargs: Function arguments
            
        Returns:
            Function result
            
        Raises:
            Exception: If circuit is open or function fails
        """
        if self.state == 'OPEN':
            if self._should_attempt_reset():
                self.state = 'HALF_OPEN'
            else:
                raise Exception("Circuit breaker is OPEN")
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        
        except Exception as e:
            self._on_failure()
            raise e
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self.last_failure_time is None:
            return False
        
        return (datetime.now() - self.last_failure_time).total_seconds() > self.recovery_timeout
    
    def _on_success(self):
        """Handle successful function execution."""
        self.failure_count = 0
        self.state = 'CLOSED'
    
    def _on_failure(self):
        """Handle failed function execution."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            self.state = 'OPEN'
