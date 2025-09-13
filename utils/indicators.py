"""
Technical Indicators for Trading Strategy
Implements RSI, PSAR, Engulfing Pattern, and Volume analysis.
"""

import numpy as np
import pandas as pd
from typing import Tuple, Optional, Dict, Any
import talib
from dataclasses import dataclass


@dataclass
class IndicatorResult:
    """Container for indicator calculation results."""
    values: np.ndarray
    signals: Optional[np.ndarray] = None
    metadata: Optional[Dict[str, Any]] = None


class TechnicalIndicators:
    """
    Technical indicators calculator for RSI-PSAR-Engulfing strategy.
    """
    
    @staticmethod
    def rsi(prices: pd.Series, period: int = 14) -> IndicatorResult:
        """
        Calculate Relative Strength Index (RSI).
        
        Args:
            prices: Close prices
            period: RSI period (default 14)
            
        Returns:
            IndicatorResult: RSI values and signals
        """
        if len(prices) < period + 1:
            # Insufficient data
            rsi_values = np.full(len(prices), np.nan)
        else:
            rsi_values = talib.RSI(prices.values, timeperiod=period)
        
        # Generate signals
        signals = np.full(len(prices), 0)  # 0 = neutral
        
        if not np.all(np.isnan(rsi_values)):
            signals[rsi_values > 70] = -1  # Overbought (sell signal)
            signals[rsi_values < 30] = 1   # Oversold (buy signal) 
            signals[rsi_values > 50] = 0.5 # Trending up
            signals[rsi_values < 50] = -0.5 # Trending down
        
        metadata = {
            'period': period,
            'overbought_level': 70,
            'oversold_level': 30,
            'neutral_level': 50,
            'current_rsi': rsi_values[-1] if not np.isnan(rsi_values[-1]) else None
        }
        
        return IndicatorResult(
            values=rsi_values,
            signals=signals,
            metadata=metadata
        )
    
    @staticmethod
    def parabolic_sar(high: pd.Series, low: pd.Series, close: pd.Series,
                      af_init: float = 0.02, af_step: float = 0.02, 
                      af_max: float = 0.20) -> IndicatorResult:
        """
        Calculate Parabolic Stop and Reverse (PSAR).
        
        Args:
            high: High prices
            low: Low prices  
            close: Close prices
            af_init: Initial acceleration factor
            af_step: Acceleration factor step
            af_max: Maximum acceleration factor
            
        Returns:
            IndicatorResult: PSAR values and trend signals
        """
        if len(close) < 2:
            psar_values = np.full(len(close), np.nan)
            signals = np.full(len(close), 0)
        else:
            psar_values = talib.SAR(
                high.values, 
                low.values, 
                acceleration=af_init, 
                maximum=af_max
            )
            
            # Generate trend signals
            signals = np.full(len(close), 0)
            price_vs_psar = close.values > psar_values
            
            # 1 = uptrend, -1 = downtrend
            signals[price_vs_psar] = 1
            signals[~price_vs_psar] = -1
        
        # Detect trend changes
        trend_changes = np.full(len(close), False)
        if len(signals) > 1:
            trend_changes[1:] = signals[1:] != signals[:-1]
        
        metadata = {
            'af_init': af_init,
            'af_step': af_step, 
            'af_max': af_max,
            'current_psar': psar_values[-1] if not np.isnan(psar_values[-1]) else None,
            'current_trend': signals[-1] if len(signals) > 0 else 0,
            'trend_changes': trend_changes
        }
        
        return IndicatorResult(
            values=psar_values,
            signals=signals,
            metadata=metadata
        )
    
    @staticmethod
    def engulfing_pattern(open_prices: pd.Series, high: pd.Series,
                         low: pd.Series, close: pd.Series,
                         min_body_ratio: float = 0.5) -> IndicatorResult:
        """
        Detect Bullish and Bearish Engulfing patterns.
        
        Args:
            open_prices: Open prices
            high: High prices
            low: Low prices
            close: Close prices
            min_body_ratio: Minimum body size ratio
            
        Returns:
            IndicatorResult: Engulfing signals (+1 bullish, -1 bearish, 0 none)
        """
        if len(close) < 2:
            return IndicatorResult(
                values=np.full(len(close), 0),
                signals=np.full(len(close), 0),
                metadata={'pattern_count': 0}
            )
        
        signals = np.full(len(close), 0)
        
        for i in range(1, len(close)):
            # Current and previous candle
            prev_open, prev_close = open_prices.iloc[i-1], close.iloc[i-1]
            curr_open, curr_close = open_prices.iloc[i], close.iloc[i]
            
            # Body sizes
            prev_body = abs(prev_close - prev_open)
            curr_body = abs(curr_close - curr_open)
            
            # Minimum body size check
            if curr_body < min_body_ratio * prev_body:
                continue
            
            # Bullish Engulfing
            # Previous candle is bearish (red), current is bullish (green)
            # Current candle completely engulfs previous candle's body
            if (prev_close < prev_open and  # Previous bearish
                curr_close > curr_open and  # Current bullish
                curr_close > prev_open and  # Current close > previous open
                curr_open < prev_close):    # Current open < previous close
                signals[i] = 1
            
            # Bearish Engulfing  
            # Previous candle is bullish (green), current is bearish (red)
            # Current candle completely engulfs previous candle's body
            elif (prev_close > prev_open and  # Previous bullish
                  curr_close < curr_open and  # Current bearish  
                  curr_close < prev_open and  # Current close < previous open
                  curr_open > prev_close):    # Current open > previous close
                signals[i] = -1
        
        # Calculate additional metadata
        bullish_count = np.sum(signals == 1)
        bearish_count = np.sum(signals == -1)
        
        # Check for engulfing in last N candles
        lookback = min(3, len(signals))
        recent_bullish = np.any(signals[-lookback:] == 1) if lookback > 0 else False
        recent_bearish = np.any(signals[-lookback:] == -1) if lookback > 0 else False
        
        metadata = {
            'min_body_ratio': min_body_ratio,
            'bullish_count': int(bullish_count),
            'bearish_count': int(bearish_count),
            'recent_bullish_engulfing': recent_bullish,
            'recent_bearish_engulfing': recent_bearish,
            'last_signal': signals[-1] if len(signals) > 0 else 0
        }
        
        return IndicatorResult(
            values=signals.astype(float),
            signals=signals,
            metadata=metadata
        )
    
    @staticmethod
    def volume_analysis(volume: pd.Series, avg_period: int = 20,
                       anomaly_threshold: float = 1.0) -> IndicatorResult:
        """
        Analyze volume patterns and anomalies.
        
        Args:
            volume: Volume data
            avg_period: Period for average volume calculation
            anomaly_threshold: Threshold multiplier for volume anomaly
            
        Returns:
            IndicatorResult: Volume averages and anomaly signals
        """
        if len(volume) < avg_period:
            # Insufficient data for full calculation
            avg_volume = np.full(len(volume), np.nan)
            # Use simple moving average for available data
            for i in range(len(volume)):
                start_idx = max(0, i - avg_period + 1)
                avg_volume[i] = volume.iloc[start_idx:i+1].mean()
        else:
            avg_volume = talib.SMA(volume.values, timeperiod=avg_period)
        
        # Volume anomaly detection
        volume_anomaly = np.full(len(volume), 0)
        
        for i in range(len(volume)):
            if not np.isnan(avg_volume[i]) and avg_volume[i] > 0:
                if volume.iloc[i] > anomaly_threshold * avg_volume[i]:
                    volume_anomaly[i] = 1
        
        # Volume trend analysis
        volume_trend = np.full(len(volume), 0)
        if len(volume) >= 5:
            # Simple trend detection over last 5 periods
            for i in range(4, len(volume)):
                recent_vol = volume.iloc[i-4:i+1]
                if recent_vol.iloc[-1] > recent_vol.iloc[0]:
                    volume_trend[i] = 1
                elif recent_vol.iloc[-1] < recent_vol.iloc[0]:
                    volume_trend[i] = -1
        
        metadata = {
            'avg_period': avg_period,
            'anomaly_threshold': anomaly_threshold,
            'current_volume': volume.iloc[-1] if len(volume) > 0 else 0,
            'current_avg_volume': avg_volume[-1] if not np.isnan(avg_volume[-1]) else 0,
            'volume_anomaly_count': np.sum(volume_anomaly == 1),
            'current_anomaly': bool(volume_anomaly[-1]) if len(volume_anomaly) > 0 else False
        }
        
        return IndicatorResult(
            values=avg_volume,
            signals=volume_anomaly,
            metadata=metadata
        )
    
    @staticmethod
    def calculate_all_indicators(df: pd.DataFrame, 
                               rsi_period: int = 14,
                               psar_af_init: float = 0.02,
                               psar_af_step: float = 0.02, 
                               psar_af_max: float = 0.20,
                               engulfing_min_body_ratio: float = 0.5,
                               volume_avg_period: int = 20,
                               volume_anomaly_threshold: float = 1.0) -> pd.DataFrame:
        """
        Calculate all indicators for a complete dataset.
        
        Args:
            df: OHLCV DataFrame with columns: open, high, low, close, volume
            Other args: Individual indicator parameters
            
        Returns:
            pd.DataFrame: Original data with added indicator columns
        """
        result_df = df.copy()
        
        # Ensure required columns exist
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")
        
        # RSI Calculation
        rsi_result = TechnicalIndicators.rsi(df['close'], period=rsi_period)
        result_df['rsi'] = rsi_result.values
        result_df['rsi_signal'] = rsi_result.signals
        
        # PSAR Calculation
        psar_result = TechnicalIndicators.parabolic_sar(
            df['high'], df['low'], df['close'],
            af_init=psar_af_init, af_step=psar_af_step, af_max=psar_af_max
        )
        result_df['psar'] = psar_result.values
        result_df['psar_trend'] = psar_result.signals
        result_df['price_vs_psar'] = (df['close'] > psar_result.values).astype(int)
        
        # Engulfing Pattern
        engulfing_result = TechnicalIndicators.engulfing_pattern(
            df['open'], df['high'], df['low'], df['close'],
            min_body_ratio=engulfing_min_body_ratio
        )
        result_df['engulfing_signal'] = engulfing_result.values
        
        # Check for engulfing in last 3 candles
        result_df['engulfing_in_3_candles'] = 0
        for i in range(len(result_df)):
            lookback_start = max(0, i - 2)
            if np.any(engulfing_result.values[lookback_start:i+1] == 1):
                result_df.iloc[i, result_df.columns.get_loc('engulfing_in_3_candles')] = 1
        
        # Volume Analysis
        volume_result = TechnicalIndicators.volume_analysis(
            df['volume'], avg_period=volume_avg_period,
            anomaly_threshold=volume_anomaly_threshold
        )
        result_df['avg_volume_20'] = volume_result.values
        result_df['volume_anomaly'] = volume_result.signals
        
        # Calculate additional derived fields
        result_df['rsi_state'] = 'neutral'
        result_df.loc[result_df['rsi'] > 70, 'rsi_state'] = 'overbought'
        result_df.loc[result_df['rsi'] < 30, 'rsi_state'] = 'oversold'
        result_df.loc[result_df['rsi'] > 50, 'rsi_state'] = 'trending_up'
        result_df.loc[result_df['rsi'] < 50, 'rsi_state'] = 'trending_down'
        
        # Body size ratio for engulfing
        body_sizes = abs(df['close'] - df['open'])
        result_df['body_size'] = body_sizes
        result_df['engulfing_body_size_ratio'] = 0.0
        
        for i in range(1, len(result_df)):
            if body_sizes.iloc[i-1] > 0:
                ratio = body_sizes.iloc[i] / body_sizes.iloc[i-1]
                result_df.iloc[i, result_df.columns.get_loc('engulfing_body_size_ratio')] = ratio
        
        return result_df


class IndicatorValidator:
    """Validator for indicator calculations and signals."""
    
    @staticmethod
    def validate_rsi(rsi_values: np.ndarray) -> Dict[str, bool]:
        """Validate RSI calculation results."""
        return {
            'values_in_range': np.all((rsi_values >= 0) & (rsi_values <= 100) | np.isnan(rsi_values)),
            'no_infinite_values': np.all(np.isfinite(rsi_values) | np.isnan(rsi_values)),
            'has_valid_values': np.any(~np.isnan(rsi_values))
        }
    
    @staticmethod  
    def validate_psar(psar_values: np.ndarray, prices: np.ndarray) -> Dict[str, bool]:
        """Validate PSAR calculation results."""
        return {
            'no_infinite_values': np.all(np.isfinite(psar_values) | np.isnan(psar_values)),
            'has_valid_values': np.any(~np.isnan(psar_values)),
            'reasonable_range': np.all(
                (psar_values >= 0.1 * np.nanmin(prices)) & 
                (psar_values <= 10 * np.nanmax(prices)) | 
                np.isnan(psar_values)
            )
        }
    
    @staticmethod
    def validate_engulfing(signals: np.ndarray) -> Dict[str, bool]:
        """Validate engulfing pattern detection."""
        return {
            'valid_signal_range': np.all((signals >= -1) & (signals <= 1)),
            'integer_signals': np.all(signals == signals.astype(int)),
            'has_patterns': np.any(signals != 0)
        }
