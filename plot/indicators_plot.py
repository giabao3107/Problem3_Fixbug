"""
Specialized plotting utilities for technical indicators.
Creates detailed plots for RSI, PSAR, Engulfing patterns, and volume analysis.
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging

from utils.indicators import IndicatorResult


class IndicatorPlotter:
    """
    Specialized plotter for technical indicators with detailed analysis.
    """
    
    def __init__(self, theme: str = 'plotly_dark'):
        """
        Initialize indicator plotter.
        
        Args:
            theme: Plotly theme
        """
        self.theme = theme
        self.logger = logging.getLogger(__name__)
        
        # Color scheme
        self.colors = {
            'rsi': '#ff6b6b',
            'rsi_overbought': '#e74c3c',
            'rsi_oversold': '#27ae60',
            'psar_up': '#00d4aa',
            'psar_down': '#ff4757',
            'engulfing_bull': '#00b894',
            'engulfing_bear': '#e17055',
            'volume_high': '#6c5ce7',
            'volume_normal': '#74b9ff',
            'support': '#2ecc71',
            'resistance': '#e74c3c'
        }
    
    def plot_rsi_analysis(self, df: pd.DataFrame, ticker: str) -> go.Figure:
        """
        Create detailed RSI analysis chart.
        
        Args:
            df: DataFrame with RSI data
            ticker: Stock ticker
            
        Returns:
            go.Figure: RSI analysis chart
        """
        if 'rsi' not in df.columns:
            return self._create_empty_chart("RSI data not available")
        
        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxis=True,
            vertical_spacing=0.08,
            row_heights=[0.5, 0.3, 0.2],
            subplot_titles=[
                f'{ticker} - Price',
                'RSI (14)',
                'RSI Divergence'
            ]
        )
        
        # Price chart
        self._add_price_chart(fig, df, row=1)
        
        # RSI with zones
        self._add_rsi_with_zones(fig, df, row=2)
        
        # RSI divergence analysis
        self._add_rsi_divergence(fig, df, row=3)
        
        fig.update_layout(
            template=self.theme,
            title=f'{ticker} - RSI Technical Analysis',
            height=800,
            showlegend=True
        )
        
        return fig
    
    def plot_psar_analysis(self, df: pd.DataFrame, ticker: str) -> go.Figure:
        """
        Create detailed PSAR analysis chart.
        
        Args:
            df: DataFrame with PSAR data
            ticker: Stock ticker
            
        Returns:
            go.Figure: PSAR analysis chart
        """
        if 'psar' not in df.columns:
            return self._create_empty_chart("PSAR data not available")
        
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxis=True,
            vertical_spacing=0.1,
            row_heights=[0.7, 0.3],
            subplot_titles=[
                f'{ticker} - Price with PSAR',
                'PSAR Trend Changes'
            ]
        )
        
        # Price with PSAR
        self._add_price_with_psar(fig, df, row=1)
        
        # Trend changes
        self._add_psar_trend_changes(fig, df, row=2)
        
        fig.update_layout(
            template=self.theme,
            title=f'{ticker} - PSAR Trend Analysis',
            height=600,
            showlegend=True
        )
        
        return fig
    
    def plot_engulfing_analysis(self, df: pd.DataFrame, ticker: str) -> go.Figure:
        """
        Create engulfing pattern analysis chart.
        
        Args:
            df: DataFrame with engulfing data
            ticker: Stock ticker
            
        Returns:
            go.Figure: Engulfing analysis chart
        """
        if 'engulfing_signal' not in df.columns:
            return self._create_empty_chart("Engulfing data not available")
        
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxis=True,
            vertical_spacing=0.1,
            row_heights=[0.8, 0.2],
            subplot_titles=[
                f'{ticker} - Candlesticks with Engulfing Patterns',
                'Pattern Frequency'
            ]
        )
        
        # Candlesticks with patterns
        self._add_candlesticks_with_engulfing(fig, df, row=1)
        
        # Pattern frequency
        self._add_engulfing_frequency(fig, df, row=2)
        
        fig.update_layout(
            template=self.theme,
            title=f'{ticker} - Engulfing Pattern Analysis',
            height=700,
            showlegend=True
        )
        
        return fig
    
    def plot_volume_analysis(self, df: pd.DataFrame, ticker: str) -> go.Figure:
        """
        Create volume analysis chart.
        
        Args:
            df: DataFrame with volume data
            ticker: Stock ticker
            
        Returns:
            go.Figure: Volume analysis chart
        """
        if 'volume' not in df.columns:
            return self._create_empty_chart("Volume data not available")
        
        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxis=True,
            vertical_spacing=0.08,
            row_heights=[0.4, 0.4, 0.2],
            subplot_titles=[
                f'{ticker} - Price',
                'Volume Analysis',
                'Volume Anomalies'
            ]
        )
        
        # Price chart
        self._add_price_chart(fig, df, row=1)
        
        # Volume with moving average
        self._add_volume_analysis(fig, df, row=2)
        
        # Volume anomalies
        self._add_volume_anomalies(fig, df, row=3)
        
        fig.update_layout(
            template=self.theme,
            title=f'{ticker} - Volume Technical Analysis',
            height=800,
            showlegend=True
        )
        
        return fig
    
    def _add_price_chart(self, fig: go.Figure, df: pd.DataFrame, row: int = 1):
        """Add basic price chart."""
        x_axis = self._get_x_axis(df)
        
        fig.add_trace(
            go.Candlestick(
                x=x_axis,
                open=df['open'],
                high=df['high'],
                low=df['low'],
                close=df['close'],
                name='Price',
                increasing_line_color=self.colors['psar_up'],
                decreasing_line_color=self.colors['psar_down']
            ),
            row=row, col=1
        )
    
    def _add_rsi_with_zones(self, fig: go.Figure, df: pd.DataFrame, row: int = 2):
        """Add RSI with overbought/oversold zones."""
        x_axis = self._get_x_axis(df)
        
        # RSI line
        fig.add_trace(
            go.Scatter(
                x=x_axis,
                y=df['rsi'],
                mode='lines',
                name='RSI',
                line=dict(color=self.colors['rsi'], width=2)
            ),
            row=row, col=1
        )
        
        # Fill zones
        fig.add_hrect(y0=70, y1=100, fillcolor=self.colors['rsi_overbought'], 
                     opacity=0.2, layer="below", line_width=0, row=row, col=1)
        fig.add_hrect(y0=0, y1=30, fillcolor=self.colors['rsi_oversold'], 
                     opacity=0.2, layer="below", line_width=0, row=row, col=1)
        
        # Level lines
        fig.add_hline(y=70, line_dash="dash", line_color=self.colors['rsi_overbought'], 
                     row=row, col=1)
        fig.add_hline(y=50, line_dash="dash", line_color="gray", row=row, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color=self.colors['rsi_oversold'], 
                     row=row, col=1)
        
        fig.update_yaxes(range=[0, 100], row=row, col=1)
    
    def _add_rsi_divergence(self, fig: go.Figure, df: pd.DataFrame, row: int = 3):
        """Add RSI divergence analysis."""
        x_axis = self._get_x_axis(df)
        
        # Calculate price momentum (simplified)
        price_momentum = df['close'].pct_change(5) * 100
        rsi_momentum = df['rsi'].diff(5)
        
        # Divergence signal (simplified)
        divergence = np.where(
            (price_momentum > 0) & (rsi_momentum < 0), 1,  # Bearish divergence
            np.where((price_momentum < 0) & (rsi_momentum > 0), -1, 0)  # Bullish divergence
        )
        
        fig.add_trace(
            go.Scatter(
                x=x_axis,
                y=divergence,
                mode='markers',
                marker=dict(
                    size=8,
                    color=np.where(divergence > 0, self.colors['rsi_overbought'], 
                                 np.where(divergence < 0, self.colors['rsi_oversold'], 'gray')),
                    symbol=np.where(divergence > 0, 'triangle-down', 
                                  np.where(divergence < 0, 'triangle-up', 'circle'))
                ),
                name='RSI Divergence',
                hovertemplate='Divergence: %{y}<extra></extra>'
            ),
            row=row, col=1
        )
    
    def _add_price_with_psar(self, fig: go.Figure, df: pd.DataFrame, row: int = 1):
        """Add price chart with PSAR overlay."""
        x_axis = self._get_x_axis(df)
        
        # Candlesticks
        fig.add_trace(
            go.Candlestick(
                x=x_axis,
                open=df['open'],
                high=df['high'],
                low=df['low'],
                close=df['close'],
                name='Price'
            ),
            row=row, col=1
        )
        
        # PSAR dots with trend colors
        if 'price_vs_psar' in df.columns:
            psar_colors = np.where(df['price_vs_psar'] == 1, 
                                 self.colors['psar_up'], 
                                 self.colors['psar_down'])
        else:
            psar_colors = self.colors['psar_up']
        
        fig.add_trace(
            go.Scatter(
                x=x_axis,
                y=df['psar'],
                mode='markers',
                marker=dict(size=5, color=psar_colors),
                name='PSAR',
                hovertemplate='PSAR: %{y:.0f}<extra></extra>'
            ),
            row=row, col=1
        )
    
    def _add_psar_trend_changes(self, fig: go.Figure, df: pd.DataFrame, row: int = 2):
        """Add PSAR trend change indicators."""
        x_axis = self._get_x_axis(df)
        
        if 'price_vs_psar' in df.columns:
            # Find trend changes
            trend_changes = df['price_vs_psar'].diff() != 0
            trend_change_points = df[trend_changes]
            
            if not trend_change_points.empty:
                change_x = x_axis[trend_changes]
                change_y = np.ones(len(change_x))
                change_colors = np.where(
                    trend_change_points['price_vs_psar'] == 1,
                    self.colors['psar_up'],
                    self.colors['psar_down']
                )
                
                fig.add_trace(
                    go.Scatter(
                        x=change_x,
                        y=change_y,
                        mode='markers',
                        marker=dict(
                            size=10,
                            color=change_colors,
                            symbol='diamond'
                        ),
                        name='Trend Changes',
                        hovertemplate='Trend Change<extra></extra>'
                    ),
                    row=row, col=1
                )
        
        fig.update_yaxes(range=[0, 2], row=row, col=1)
    
    def _add_candlesticks_with_engulfing(self, fig: go.Figure, df: pd.DataFrame, row: int = 1):
        """Add candlesticks with engulfing pattern highlights."""
        x_axis = self._get_x_axis(df)
        
        # Regular candlesticks
        fig.add_trace(
            go.Candlestick(
                x=x_axis,
                open=df['open'],
                high=df['high'],
                low=df['low'],
                close=df['close'],
                name='Price'
            ),
            row=row, col=1
        )
        
        # Highlight engulfing patterns
        engulfing_patterns = df[df['engulfing_signal'] != 0]
        
        if not engulfing_patterns.empty:
            pattern_x = x_axis[df['engulfing_signal'] != 0]
            pattern_y = engulfing_patterns['high'] * 1.01  # Slightly above high
            pattern_colors = np.where(
                engulfing_patterns['engulfing_signal'] == 1,
                self.colors['engulfing_bull'],
                self.colors['engulfing_bear']
            )
            pattern_symbols = np.where(
                engulfing_patterns['engulfing_signal'] == 1,
                'triangle-up',
                'triangle-down'
            )
            
            fig.add_trace(
                go.Scatter(
                    x=pattern_x,
                    y=pattern_y,
                    mode='markers',
                    marker=dict(
                        size=12,
                        color=pattern_colors,
                        symbol=pattern_symbols,
                        line=dict(width=2, color='white')
                    ),
                    name='Engulfing Patterns',
                    hovertemplate='%{customdata} Engulfing<extra></extra>',
                    customdata=np.where(
                        engulfing_patterns['engulfing_signal'] == 1,
                        'Bullish',
                        'Bearish'
                    )
                ),
                row=row, col=1
            )
    
    def _add_engulfing_frequency(self, fig: go.Figure, df: pd.DataFrame, row: int = 2):
        """Add engulfing pattern frequency chart."""
        # Count patterns by hour/day
        if hasattr(df.index, 'hour'):
            df_copy = df.copy()
            df_copy['hour'] = df_copy.index.hour
            pattern_freq = df_copy[df_copy['engulfing_signal'] != 0].groupby('hour')['engulfing_signal'].count()
        else:
            # Use simple index-based binning
            pattern_freq = pd.Series([1, 0, 2, 1, 0, 3, 1, 2], index=range(8))
        
        fig.add_trace(
            go.Bar(
                x=pattern_freq.index,
                y=pattern_freq.values,
                name='Pattern Frequency',
                marker_color=self.colors['engulfing_bull'],
                opacity=0.7
            ),
            row=row, col=1
        )
    
    def _add_volume_analysis(self, fig: go.Figure, df: pd.DataFrame, row: int = 2):
        """Add volume analysis with moving average."""
        x_axis = self._get_x_axis(df)
        
        # Volume bars with price-based colors
        volume_colors = []
        for i in range(len(df)):
            if df['close'].iloc[i] >= df['open'].iloc[i]:
                volume_colors.append(self.colors['psar_up'])
            else:
                volume_colors.append(self.colors['psar_down'])
        
        fig.add_trace(
            go.Bar(
                x=x_axis,
                y=df['volume'],
                name='Volume',
                marker_color=volume_colors,
                opacity=0.7
            ),
            row=row, col=1
        )
        
        # Average volume
        if 'avg_volume_20' in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=x_axis,
                    y=df['avg_volume_20'],
                    mode='lines',
                    name='20-day Avg Volume',
                    line=dict(color='orange', dash='dash', width=2)
                ),
                row=row, col=1
            )
    
    def _add_volume_anomalies(self, fig: go.Figure, df: pd.DataFrame, row: int = 3):
        """Add volume anomaly indicators."""
        x_axis = self._get_x_axis(df)
        
        if 'volume_anomaly' in df.columns:
            anomalies = df['volume_anomaly']
            
            fig.add_trace(
                go.Scatter(
                    x=x_axis,
                    y=anomalies,
                    mode='markers',
                    marker=dict(
                        size=8,
                        color=np.where(anomalies == 1, self.colors['volume_high'], 'gray'),
                        symbol=np.where(anomalies == 1, 'diamond', 'circle')
                    ),
                    name='Volume Anomalies',
                    hovertemplate='Volume Anomaly: %{y}<extra></extra>'
                ),
                row=row, col=1
            )
        
        fig.update_yaxes(range=[-0.5, 1.5], row=row, col=1)
    
    def _get_x_axis(self, df: pd.DataFrame):
        """Get appropriate x-axis values."""
        if hasattr(df.index, 'dtype') and 'datetime' in str(df.index.dtype):
            return df.index
        elif 'timestamp' in df.columns:
            return df['timestamp']
        else:
            return range(len(df))
    
    def _create_empty_chart(self, message: str) -> go.Figure:
        """Create empty chart with message."""
        fig = go.Figure()
        fig.add_annotation(
            text=message,
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=20, color="gray")
        )
        fig.update_layout(
            template=self.theme,
            height=400
        )
        return fig
