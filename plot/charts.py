"""
Chart generation utilities for trading analysis.
Creates various types of charts for market data and signals.
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging

from strategy.rsi_psar_engulfing import TradingSignal
from utils.helpers import format_currency, format_percentage


class ChartGenerator:
    """
    Main chart generator for trading data visualization.
    """
    
    def __init__(self, theme: str = 'plotly_dark'):
        """
        Initialize chart generator.
        
        Args:
            theme: Plotly theme to use
        """
        self.theme = theme
        self.logger = logging.getLogger(__name__)
        
        # Chart colors
        self.colors = {
            'bullish': '#00d4aa',
            'bearish': '#ff4757',
            'neutral': '#747d8c',
            'volume': '#5f27cd',
            'rsi': '#ff6b6b',
            'psar': '#feca57',
            'signal_buy': '#00b894',
            'signal_sell': '#e74c3c',
            'signal_risk': '#fdcb6e'
        }
    
    def create_ohlc_chart(self, df: pd.DataFrame, ticker: str,
                         show_volume: bool = True,
                         show_indicators: bool = True,
                         signals: List[TradingSignal] = None) -> go.Figure:
        """
        Create OHLC chart with indicators and signals.
        
        Args:
            df: OHLCV DataFrame with indicators
            ticker: Stock ticker
            show_volume: Whether to show volume subplot
            show_indicators: Whether to show technical indicators
            signals: Trading signals to overlay
            
        Returns:
            go.Figure: Complete chart figure
        """
        if df.empty:
            return self._create_empty_chart(f"No data for {ticker}")
        
        # Determine subplot structure
        if show_volume and show_indicators:
            fig = make_subplots(
                rows=3, cols=1,
                shared_xaxis=True,
                vertical_spacing=0.05,
                row_heights=[0.6, 0.25, 0.15],
                subplot_titles=[
                    f'{ticker} - Price & Indicators',
                    'RSI',
                    'Volume'
                ]
            )
        elif show_indicators:
            fig = make_subplots(
                rows=2, cols=1,
                shared_xaxis=True,
                vertical_spacing=0.08,
                row_heights=[0.7, 0.3],
                subplot_titles=[
                    f'{ticker} - Price & Indicators',
                    'RSI'
                ]
            )
        elif show_volume:
            fig = make_subplots(
                rows=2, cols=1,
                shared_xaxis=True,
                vertical_spacing=0.08,
                row_heights=[0.8, 0.2],
                subplot_titles=[
                    f'{ticker} - Price',
                    'Volume'
                ]
            )
        else:
            fig = go.Figure()
        
        # Add OHLC candlesticks
        self._add_candlestick(fig, df, row=1)
        
        # Add PSAR if available
        if 'psar' in df.columns and not df['psar'].isna().all():
            self._add_psar(fig, df, row=1)
        
        # Add RSI if requested and available
        if show_indicators and 'rsi' in df.columns:
            rsi_row = 2
            self._add_rsi(fig, df, row=rsi_row)
        
        # Add volume if requested
        if show_volume:
            volume_row = 3 if show_indicators else 2
            self._add_volume(fig, df, row=volume_row)
        
        # Add trading signals
        if signals:
            self._add_signals(fig, df, signals)
        
        # Update layout
        self._update_chart_layout(fig, ticker)
        
        return fig
    
    def _add_candlestick(self, fig: go.Figure, df: pd.DataFrame, row: int = 1):
        """Add candlestick trace."""
        x_axis = df.index if hasattr(df.index, 'dtype') and 'datetime' in str(df.index.dtype) else df.get('timestamp', range(len(df)))
        
        fig.add_trace(
            go.Candlestick(
                x=x_axis,
                open=df['open'],
                high=df['high'],
                low=df['low'],
                close=df['close'],
                name='Price',
                increasing_line_color=self.colors['bullish'],
                decreasing_line_color=self.colors['bearish']
            ),
            row=row, col=1
        )
    
    def _add_psar(self, fig: go.Figure, df: pd.DataFrame, row: int = 1):
        """Add PSAR indicators."""
        x_axis = df.index if hasattr(df.index, 'dtype') and 'datetime' in str(df.index.dtype) else df.get('timestamp', range(len(df)))
        
        # Color PSAR dots based on trend
        psar_colors = []
        if 'price_vs_psar' in df.columns:
            for psar_signal in df['price_vs_psar']:
                if psar_signal == 1:
                    psar_colors.append(self.colors['bullish'])
                else:
                    psar_colors.append(self.colors['bearish'])
        else:
            psar_colors = [self.colors['psar']] * len(df)
        
        fig.add_trace(
            go.Scatter(
                x=x_axis,
                y=df['psar'],
                mode='markers',
                marker=dict(
                    size=4,
                    color=psar_colors,
                    symbol='circle'
                ),
                name='PSAR',
                hovertemplate='PSAR: %{y:.0f}<extra></extra>'
            ),
            row=row, col=1
        )
    
    def _add_rsi(self, fig: go.Figure, df: pd.DataFrame, row: int = 2):
        """Add RSI indicator."""
        x_axis = df.index if hasattr(df.index, 'dtype') and 'datetime' in str(df.index.dtype) else df.get('timestamp', range(len(df)))
        
        # RSI line
        fig.add_trace(
            go.Scatter(
                x=x_axis,
                y=df['rsi'],
                mode='lines',
                name='RSI',
                line=dict(color=self.colors['rsi'], width=2),
                hovertemplate='RSI: %{y:.1f}<extra></extra>'
            ),
            row=row, col=1
        )
        
        # RSI levels
        fig.add_hline(y=70, line_dash="dash", line_color="red", 
                     annotation_text="Overbought", row=row, col=1)
        fig.add_hline(y=50, line_dash="dash", line_color="gray", 
                     annotation_text="Neutral", row=row, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", 
                     annotation_text="Oversold", row=row, col=1)
        
        # Set RSI y-axis range
        fig.update_yaxes(range=[0, 100], row=row, col=1)
    
    def _add_volume(self, fig: go.Figure, df: pd.DataFrame, row: int = 3):
        """Add volume bars."""
        x_axis = df.index if hasattr(df.index, 'dtype') and 'datetime' in str(df.index.dtype) else df.get('timestamp', range(len(df)))
        
        # Color volume bars
        volume_colors = []
        for i in range(len(df)):
            if df['close'].iloc[i] >= df['open'].iloc[i]:
                volume_colors.append(self.colors['bullish'])
            else:
                volume_colors.append(self.colors['bearish'])
        
        fig.add_trace(
            go.Bar(
                x=x_axis,
                y=df['volume'],
                name='Volume',
                marker_color=volume_colors,
                opacity=0.7,
                hovertemplate='Volume: %{y:,.0f}<extra></extra>'
            ),
            row=row, col=1
        )
        
        # Add average volume if available
        if 'avg_volume_20' in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=x_axis,
                    y=df['avg_volume_20'],
                    mode='lines',
                    name='Avg Volume',
                    line=dict(color='orange', dash='dash', width=1),
                    hovertemplate='Avg Volume: %{y:,.0f}<extra></extra>'
                ),
                row=row, col=1
            )
    
    def _add_signals(self, fig: go.Figure, df: pd.DataFrame, signals: List[TradingSignal]):
        """Add trading signals as annotations."""
        for signal in signals:
            # Find closest timestamp in data
            signal_time = signal.timestamp
            signal_price = signal.entry_price
            
            # Determine signal properties
            if signal.signal_type == 'buy':
                color = self.colors['signal_buy']
                symbol = 'triangle-up'
                text = f"BUY<br>{format_currency(signal_price)}<br>{signal.confidence:.0%}"
            elif signal.signal_type == 'sell':
                color = self.colors['signal_sell']
                symbol = 'triangle-down'
                text = f"SELL<br>{format_currency(signal_price)}<br>{signal.confidence:.0%}"
            else:  # risk_warning
                color = self.colors['signal_risk']
                symbol = 'diamond'
                text = f"RISK<br>{format_currency(signal_price)}"
            
            # Add marker
            fig.add_trace(
                go.Scatter(
                    x=[signal_time],
                    y=[signal_price],
                    mode='markers+text',
                    marker=dict(
                        size=12,
                        color=color,
                        symbol=symbol,
                        line=dict(width=2, color='white')
                    ),
                    text=[text],
                    textposition="top center",
                    textfont=dict(size=10, color=color),
                    name=f'{signal.signal_type.title()} Signal',
                    hovertemplate=f'{signal.reason}<br>Confidence: {signal.confidence:.0%}<extra></extra>',
                    showlegend=False
                ),
                row=1, col=1
            )
    
    def _update_chart_layout(self, fig: go.Figure, ticker: str):
        """Update chart layout and styling."""
        fig.update_layout(
            template=self.theme,
            title=f"{ticker} Trading Chart",
            xaxis_rangeslider_visible=False,
            height=700,
            showlegend=True,
            legend=dict(
                yanchor="top",
                y=0.99,
                xanchor="left",
                x=0.01
            )
        )
        
        # Remove x-axis labels for all but bottom subplot
        fig.update_xaxes(showticklabels=False, row=1, col=1)
        if fig._get_subplot(2, 1):
            fig.update_xaxes(showticklabels=False, row=2, col=1)
    
    def _create_empty_chart(self, title: str) -> go.Figure:
        """Create empty chart with message."""
        fig = go.Figure()
        fig.add_annotation(
            text=title,
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=20, color="gray")
        )
        fig.update_layout(
            template=self.theme,
            height=400,
            showlegend=False
        )
        return fig
    
    def create_performance_chart(self, signals: List[TradingSignal],
                               portfolio_value: float = 1000000) -> go.Figure:
        """Create performance tracking chart."""
        if not signals:
            return self._create_empty_chart("No trading signals available")
        
        # Convert signals to DataFrame
        signal_data = []
        cumulative_pnl = 0
        
        for signal in signals:
            if signal.signal_type in ['buy', 'sell']:
                # Simulate P&L (in real system, this would come from actual trades)
                if signal.signal_type == 'sell':
                    pnl = np.random.normal(0.02, 0.05) * portfolio_value * 0.02  # 2% position size
                    cumulative_pnl += pnl
                
                signal_data.append({
                    'timestamp': signal.timestamp,
                    'type': signal.signal_type,
                    'ticker': signal.ticker,
                    'price': signal.entry_price,
                    'cumulative_pnl': cumulative_pnl
                })
        
        if not signal_data:
            return self._create_empty_chart("No completed trades available")
        
        df = pd.DataFrame(signal_data)
        
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxis=True,
            vertical_spacing=0.1,
            row_heights=[0.7, 0.3],
            subplot_titles=['Cumulative P&L', 'Trading Activity']
        )
        
        # Cumulative P&L line
        fig.add_trace(
            go.Scatter(
                x=df['timestamp'],
                y=df['cumulative_pnl'],
                mode='lines',
                name='Cumulative P&L',
                line=dict(color=self.colors['bullish'], width=2),
                fill='tonexty',
                hovertemplate='P&L: %{y:,.0f} VND<extra></extra>'
            ),
            row=1, col=1
        )
        
        # Trading signals
        buy_signals = df[df['type'] == 'buy']
        sell_signals = df[df['type'] == 'sell']
        
        if not buy_signals.empty:
            fig.add_trace(
                go.Scatter(
                    x=buy_signals['timestamp'],
                    y=buy_signals['cumulative_pnl'],
                    mode='markers',
                    marker=dict(
                        size=8,
                        color=self.colors['signal_buy'],
                        symbol='triangle-up'
                    ),
                    name='Buy Signals',
                    hovertemplate='Buy: %{customdata}<extra></extra>',
                    customdata=buy_signals['ticker']
                ),
                row=1, col=1
            )
        
        if not sell_signals.empty:
            fig.add_trace(
                go.Scatter(
                    x=sell_signals['timestamp'],
                    y=sell_signals['cumulative_pnl'],
                    mode='markers',
                    marker=dict(
                        size=8,
                        color=self.colors['signal_sell'],
                        symbol='triangle-down'
                    ),
                    name='Sell Signals',
                    hovertemplate='Sell: %{customdata}<extra></extra>',
                    customdata=sell_signals['ticker']
                ),
                row=1, col=1
            )
        
        # Trading activity histogram
        df['hour'] = df['timestamp'].dt.hour
        hourly_activity = df['hour'].value_counts().sort_index()
        
        fig.add_trace(
            go.Bar(
                x=hourly_activity.index,
                y=hourly_activity.values,
                name='Trades per Hour',
                marker_color=self.colors['volume'],
                opacity=0.7
            ),
            row=2, col=1
        )
        
        fig.update_layout(
            template=self.theme,
            title='Trading Performance Overview',
            height=600,
            showlegend=True
        )
        
        return fig


class SignalVisualizer:
    """
    Specialized visualizer for trading signals.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def create_signal_heatmap(self, signals: List[TradingSignal]) -> go.Figure:
        """Create heatmap of signals by ticker and time."""
        if not signals:
            return go.Figure().add_annotation(
                text="No signals available",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False
            )
        
        # Convert to DataFrame
        signal_data = []
        for signal in signals:
            signal_data.append({
                'ticker': signal.ticker,
                'hour': signal.timestamp.hour,
                'confidence': signal.confidence,
                'type': signal.signal_type
            })
        
        df = pd.DataFrame(signal_data)
        
        # Create pivot table
        heatmap_data = df.pivot_table(
            values='confidence',
            index='ticker',
            columns='hour',
            aggfunc='mean',
            fill_value=0
        )
        
        fig = go.Figure(data=go.Heatmap(
            z=heatmap_data.values,
            x=[f"{h:02d}:00" for h in heatmap_data.columns],
            y=heatmap_data.index,
            colorscale='RdYlGn',
            text=[[f"{val:.0%}" if val > 0 else "" for val in row] for row in heatmap_data.values],
            texttemplate="%{text}",
            textfont={"size": 10},
            hoverongaps=False,
            hovertemplate='Time: %{x}<br>Ticker: %{y}<br>Avg Confidence: %{z:.0%}<extra></extra>'
        ))
        
        fig.update_layout(
            title="Signal Confidence Heatmap (by Hour)",
            xaxis_title="Hour of Day",
            yaxis_title="Ticker",
            height=400
        )
        
        return fig
    
    def create_confidence_distribution(self, signals: List[TradingSignal]) -> go.Figure:
        """Create confidence distribution chart."""
        if not signals:
            return go.Figure()
        
        confidences = [s.confidence for s in signals]
        
        fig = go.Figure()
        
        fig.add_trace(go.Histogram(
            x=confidences,
            nbinsx=20,
            name='Signal Confidence Distribution',
            marker_color='skyblue',
            opacity=0.7
        ))
        
        fig.update_layout(
            title='Signal Confidence Distribution',
            xaxis_title='Confidence Level',
            yaxis_title='Count',
            height=400
        )
        
        return fig
