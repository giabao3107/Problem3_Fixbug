"""
Streamlit Dashboard for Real-time Trading Alerts
Displays live signals, charts, and portfolio monitoring.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
from datetime import datetime, timedelta
import time
import json
from typing import Dict, List, Optional, Any

from utils.helpers import load_config, format_currency, format_percentage
from utils.fiinquant_adapter import FiinQuantAdapter, MarketDataPoint
from utils.indicators import TechnicalIndicators
from strategy.rsi_psar_engulfing import RSIPSAREngulfingStrategy, TradingSignal


# Page configuration
st.set_page_config(
    page_title="Trading Alert Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)


class DashboardData:
    """Data management for dashboard."""
    
    def __init__(self):
        self.signals: List[TradingSignal] = []
        self.market_data: Dict[str, pd.DataFrame] = {}
        self.portfolio_stats = {}
        self.last_update = datetime.now()
    
    def add_signal(self, signal: TradingSignal):
        """Add new signal to dashboard."""
        self.signals.append(signal)
        # Keep last 100 signals
        if len(self.signals) > 100:
            self.signals = self.signals[-100:]
    
    def update_market_data(self, ticker: str, df: pd.DataFrame):
        """Update market data for ticker."""
        self.market_data[ticker] = df
        self.last_update = datetime.now()
    
    def get_recent_signals(self, hours: int = 24) -> List[TradingSignal]:
        """Get signals from last N hours."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [s for s in self.signals if s.timestamp > cutoff_time]


@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_dashboard_config():
    """Load configuration for dashboard."""
    return load_config()


@st.cache_resource
def initialize_components():
    """Initialize dashboard components."""
    config = load_dashboard_config()
    
    # Initialize FiinQuant adapter
    import os
    username = os.getenv('FIINQUANT_USERNAME')
    password = os.getenv('FIINQUANT_PASSWORD')
    
    if not username or not password:
        st.error("⚠️ FiinQuant credentials not found. Please set FIINQUANT_USERNAME and FIINQUANT_PASSWORD in .env file.")
        st.stop()
    
    adapter = FiinQuantAdapter(username, password)
    
    # Initialize strategy
    strategy = RSIPSAREngulfingStrategy(config)
    
    return config, adapter, strategy


def fetch_real_data(adapter: FiinQuantAdapter, tickers: List[str], periods: int = 100) -> Dict[str, pd.DataFrame]:
    """Fetch real market data from FiinQuant."""
    data = {}
    
    try:
        # Login to FiinQuant
        if not adapter.login():
            st.error("❌ Failed to login to FiinQuant")
            return {}
        
        for ticker in tickers:
            try:
                # Fetch historical data
                df = adapter.fetch_historical_data([ticker], timeframe='15m', period=periods)
                
                if not df.empty:
                    # Add indicators
                    df = TechnicalIndicators.calculate_all_indicators(df)
                    data[ticker] = df
                else:
                    st.warning(f"⚠️ No data received for {ticker}")
                    
            except Exception as e:
                st.error(f"❌ Error fetching data for {ticker}: {str(e)}")
                continue
        
        return data
        
    except Exception as e:
        st.error(f"❌ FiinQuant connection error: {str(e)}")
        return {}


def create_signals_table(signals: List[TradingSignal]) -> pd.DataFrame:
    """Create DataFrame for signals table."""
    if not signals:
        return pd.DataFrame()
    
    data = []
    for signal in signals:
        data.append({
            'Thời gian': signal.timestamp.strftime('%H:%M:%S'),
            'Mã': signal.ticker,
            'Loại': signal.signal_type.upper(),
            'Giá': signal.entry_price,
            'Tin cậy': f"{signal.confidence:.0%}",
            'Lý do': signal.reason[:30] + '...' if len(signal.reason) > 30 else signal.reason
        })
    
    return pd.DataFrame(data)


def filter_trading_days(df: pd.DataFrame) -> pd.DataFrame:
    """Filter out non-trading days (weekends and holidays) from DataFrame."""
    if df.empty:
        return df
    
    # Ensure timestamp is datetime
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        # Filter out weekends (Saturday=5, Sunday=6)
        df = df[df['timestamp'].dt.dayofweek < 5]
        # Remove rows where volume is 0 or NaN (likely holidays)
        if 'volume' in df.columns:
            df = df[(df['volume'] > 0) & (df['volume'].notna())]
    
    return df.reset_index(drop=True)

def create_ohlc_chart(df: pd.DataFrame, ticker: str) -> go.Figure:
    """Create OHLC chart with indicators."""
    if df.empty:
        return go.Figure()
    
    # Filter out non-trading days for continuous chart
    df = filter_trading_days(df)
    
    # Create subplots
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.6, 0.2, 0.2],
        subplot_titles=[f'{ticker} - Price & PSAR', 'RSI', 'Volume']
    )
    
    # OHLC candlestick
    fig.add_trace(
        go.Candlestick(
            x=df['timestamp'],
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name='Price'
        ),
        row=1, col=1
    )
    
    # PSAR
    if 'psar' in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df['timestamp'],
                y=df['psar'],
                mode='markers',
                marker=dict(size=3, color='orange'),
                name='PSAR'
            ),
            row=1, col=1
        )
    
    # RSI
    if 'rsi' in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df['timestamp'],
                y=df['rsi'],
                mode='lines',
                name='RSI',
                line=dict(color='purple')
            ),
            row=2, col=1
        )
        
        # RSI levels
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)
        fig.add_hline(y=50, line_dash="dash", line_color="gray", row=2, col=1)
    
    # Volume
    fig.add_trace(
        go.Bar(
            x=df['timestamp'],
            y=df['volume'],
            name='Volume',
            marker_color='lightblue'
        ),
        row=3, col=1
    )
    
    # Add volume average if available
    if 'avg_volume_20' in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df['timestamp'],
                y=df['avg_volume_20'],
                mode='lines',
                name='Avg Volume',
                line=dict(color='red', dash='dash')
            ),
            row=3, col=1
        )
    
    # Update layout
    fig.update_layout(
        height=700,
        showlegend=True,
        xaxis_rangeslider_visible=False,
        title_x=0.5
    )
    
    # Configure x-axis for continuous trading days display
    fig.update_xaxes(
        type='category',  # Use category type to avoid gaps
        showticklabels=False, 
        row=1, col=1
    )
    fig.update_xaxes(
        type='category',
        showticklabels=False, 
        row=2, col=1
    )
    fig.update_xaxes(
        type='category',
        tickformat='%Y-%m-%d',
        row=3, col=1
    )
    
    return fig


def create_signals_heatmap(signals: List[TradingSignal]) -> go.Figure:
    """Create heatmap of signals by ticker and time."""
    if not signals:
        return go.Figure()
    
    # Convert to DataFrame
    df = pd.DataFrame([
        {
            'ticker': s.ticker,
            'hour': s.timestamp.hour,
            'confidence': s.confidence,
            'type': s.signal_type
        }
        for s in signals
    ])
    
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
        hoverongaps=False
    ))
    
    fig.update_layout(
        title="Signals Confidence Heatmap (by Hour)",
        xaxis_title="Hour",
        yaxis_title="Ticker",
        height=400
    )
    
    return fig


def main():
    """Main dashboard function."""
    
    # Initialize session state
    if 'dashboard_data' not in st.session_state:
        st.session_state.dashboard_data = DashboardData()
    
    if 'last_refresh' not in st.session_state:
        st.session_state.last_refresh = datetime.now()
    
    # Initialize components
    config, adapter, strategy = initialize_components()
    
    # Sidebar
    st.sidebar.title("⚙️ Dashboard Settings")
    
    # Auto refresh toggle
    auto_refresh = st.sidebar.checkbox("Auto Refresh", value=True)
    refresh_interval = st.sidebar.slider("Refresh Interval (seconds)", 5, 60, 10)
    
    # Ticker selection
    available_tickers = ['ACB', 'VNM', 'HPG', 'VIC', 'TCB', 'FPT', 'MSN', 'VPB']
    selected_tickers = st.sidebar.multiselect(
        "Select Tickers",
        available_tickers,
        default=['ACB', 'VNM', 'HPG']
    )
    
    # Time range
    time_range = st.sidebar.selectbox(
        "Time Range",
        ['1H', '4H', '1D', '3D', '1W'],
        index=2
    )
    
    # Signal filters
    st.sidebar.subheader("🔍 Signal Filters")
    min_confidence = st.sidebar.slider("Minimum Confidence", 0.0, 1.0, 0.6, 0.05)
    signal_types = st.sidebar.multiselect(
        "Signal Types",
        ['buy', 'sell', 'risk_warning'],
        default=['buy', 'sell', 'risk_warning']
    )
    
    # Manual refresh button
    if st.sidebar.button("🔄 Refresh Now"):
        st.session_state.last_refresh = datetime.now()
        st.rerun()
    
    # Main content
    st.title("📊 Real-time Trading Dashboard")
    st.markdown("---")
    
    # Status bar
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Market Status",
            "🟢 Open" if datetime.now().hour < 15 else "🔴 Closed",
            ""
        )
    
    with col2:
        st.metric(
            "Active Signals",
            len(st.session_state.dashboard_data.get_recent_signals(1)),
            "Last 1H"
        )
    
    with col3:
        st.metric(
            "Monitored Tickers",
            len(selected_tickers),
            ""
        )
    
    with col4:
        st.metric(
            "Last Update",
            st.session_state.last_refresh.strftime("%H:%M:%S"),
            ""
        )
    
    # Fetch real data from FiinQuant
    if selected_tickers:
        with st.spinner('🔄 Fetching data from FiinQuant...'):
            real_data = fetch_real_data(adapter, selected_tickers, 100)
        
        # Generate signals from real data
        for ticker, df in real_data.items():
            signals = strategy.analyze_ticker(ticker, df)
            for signal in signals:
                if (signal.confidence >= min_confidence and 
                    signal.signal_type in signal_types):
                    st.session_state.dashboard_data.add_signal(signal)
    
    # Get recent signals
    recent_signals = st.session_state.dashboard_data.get_recent_signals(24)
    
    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📈 Charts", "🚨 Signals", "💼 Portfolio", "📊 Analytics"])
    
    with tab1:
        st.subheader("Price Charts with Indicators")
        
        if selected_tickers:
            # Chart selector
            chart_ticker = st.selectbox("Select Ticker for Chart", selected_tickers)
            
            if chart_ticker and chart_ticker in real_data:
                df = real_data[chart_ticker]
                fig = create_ohlc_chart(df, chart_ticker)
                st.plotly_chart(fig, width='stretch')
                
                # Current values
                current_row = df.iloc[-1]
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric(
                        "Current Price",
                        format_currency(current_row['close']),
                        f"{(current_row['close'] - current_row['open'])/current_row['open']*100:+.2f}%"
                    )
                
                with col2:
                    if 'rsi' in current_row:
                        st.metric(
                            "RSI",
                            f"{current_row['rsi']:.1f}",
                            "Overbought" if current_row['rsi'] > 70 else "Oversold" if current_row['rsi'] < 30 else "Neutral"
                        )
                
                with col3:
                    if 'psar' in current_row and 'price_vs_psar' in current_row:
                        st.metric(
                            "PSAR Trend",
                            "🟢 Up" if current_row['price_vs_psar'] else "🔴 Down",
                            format_currency(current_row['psar'])
                        )
                
                with col4:
                    if 'volume_anomaly' in current_row:
                        st.metric(
                            "Volume",
                            "🔥 High" if current_row['volume_anomaly'] else "📊 Normal",
                            f"{current_row['volume']:,}"
                        )
    
    with tab2:
        st.subheader("Recent Trading Signals")
        
        # Signal summary
        buy_signals = [s for s in recent_signals if s.signal_type == 'buy']
        sell_signals = [s for s in recent_signals if s.signal_type == 'sell']
        risk_signals = [s for s in recent_signals if s.signal_type == 'risk_warning']
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("🟢 Buy Signals", len(buy_signals), "24H")
        
        with col2:
            st.metric("🔴 Sell Signals", len(sell_signals), "24H")
        
        with col3:
            st.metric("🟠 Risk Warnings", len(risk_signals), "24H")
        
        # Signals tables
        if buy_signals:
            st.subheader("🟢 Buy Signals")
            buy_df = create_signals_table(buy_signals)
            st.dataframe(buy_df, width='stretch')
        
        if sell_signals:
            st.subheader("🔴 Sell Signals")
            sell_df = create_signals_table(sell_signals)
            st.dataframe(sell_df, width='stretch')
        
        if risk_signals:
            st.subheader("🟠 Risk Warnings")
            risk_df = create_signals_table(risk_signals)
            st.dataframe(risk_df, width='stretch')
        
        if not recent_signals:
            st.info("No recent signals. Waiting for market data...")
    
    with tab3:
        st.subheader("Portfolio Overview")
        
        # Mock portfolio data
        portfolio_data = {
            'Total Value': 1000000000,  # 1B VND
            'Cash': 200000000,          # 200M VND
            'Positions': 8,
            'Max Positions': 10,
            'Daily P&L': 0.025,         # 2.5%
            'Total Return': 0.15,       # 15%
            'Max Drawdown': -0.08,      # -8%
            'Win Rate': 0.65            # 65%
        }
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "Portfolio Value",
                format_currency(portfolio_data['Total Value']),
                f"{portfolio_data['Daily P&L']:+.2%} today".replace('%', ' percent')
            )
        
        with col2:
            cash_pct = portfolio_data['Cash']/portfolio_data['Total Value']
            st.metric(
                "Available Cash",
                format_currency(portfolio_data['Cash']),
                f"{cash_pct:.0%} of portfolio".replace('%', ' percent')
            )
        
        with col3:
            util_pct = portfolio_data['Positions']/portfolio_data['Max Positions']
            st.metric(
                "Active Positions",
                f"{portfolio_data['Positions']}/{portfolio_data['Max Positions']}",
                f"{util_pct:.0%} utilization".replace('%', ' percent')
            )
        
        with col4:
            st.metric(
                "Win Rate",
                f"{portfolio_data['Win Rate']:.0%}".replace('%', ' percent'),
                f"Max DD: {portfolio_data['Max Drawdown']:+.1%}".replace('%', ' percent')
            )
        
        # Position details (mock)
        st.subheader("Position Details")
        
        positions_df = pd.DataFrame({
            'Ticker': ['ACB', 'VNM', 'HPG', 'FPT'],
            'Shares': [1000, 500, 2000, 800],
            'Entry Price': [25000, 45000, 35000, 65000],
            'Current Price': [26500, 44000, 36200, 67500],
            'P&L %': ['+6.0%', '-2.2%', '+3.4%', '+3.8%'],
            'Value (VND)': ['26,500,000', '22,000,000', '72,400,000', '54,000,000']
        })
        
        st.dataframe(positions_df, width='stretch')
    
    with tab4:
        st.subheader("Analytics & Performance")
        
        # Signals heatmap
        if recent_signals:
            st.subheader("Signals Heatmap")
            heatmap_fig = create_signals_heatmap(recent_signals)
            st.plotly_chart(heatmap_fig, width='stretch')
        
        # Performance metrics
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Signal Statistics")
            
            if recent_signals:
                # Convert percentage to string to avoid PyArrow issues
                avg_confidence = np.mean([s.confidence for s in recent_signals])
                signal_stats = pd.DataFrame({
                    'Metric': ['Total Signals', 'Avg Confidence', 'High Confidence', 'Low Confidence'],
                    'Value': [
                        str(len(recent_signals)),
                        f"{avg_confidence:.1%}",
                        str(len([s for s in recent_signals if s.confidence > 0.8])),
                        str(len([s for s in recent_signals if s.confidence < 0.6]))
                    ]
                })
                st.dataframe(signal_stats, hide_index=True)
        
        with col2:
            st.subheader("Market Coverage")
            
            if recent_signals:
                ticker_counts = {}
                for signal in recent_signals:
                    ticker_counts[signal.ticker] = ticker_counts.get(signal.ticker, 0) + 1
                
                coverage_df = pd.DataFrame([
                    {'Ticker': ticker, 'Signals': count}
                    for ticker, count in sorted(ticker_counts.items(), key=lambda x: x[1], reverse=True)
                ])
                
                st.dataframe(coverage_df, hide_index=True)
    
    # Footer
    st.markdown("---")
    st.markdown(
        f"*Dashboard updated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
        f"Refresh interval: {refresh_interval}s*"
    )
    
    # Auto refresh
    if auto_refresh:
        time.sleep(refresh_interval)
        st.rerun()


if __name__ == "__main__":
    main()
