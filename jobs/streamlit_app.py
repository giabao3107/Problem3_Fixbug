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
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for professional styling
st.markdown("""
<style>
    /* Trading theme colors */
    :root {
        --primary-color: #00d4aa;
        --secondary-color: #1a1a2e;
        --success-color: #00ff88;
        --danger-color: #ff4757;
        --warning-color: #ffa502;
        --dark-bg: #0f0f23;
        --card-bg: #16213e;
        --text-primary: #ffffff;
        --text-secondary: #8892b0;
        --accent-color: #64ffda;
        --bull-color: #26a69a;
        --bear-color: #ef5350;
        --focus-color: #00d4aa;
        --focus-width: 2px;
    }
    
    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Custom sidebar styling */
    .css-1d391kg {
        background: linear-gradient(180deg, var(--secondary-color) 0%, var(--dark-bg) 100%);
    }
    
    /* Main content area */
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 100%;
    }
    
    /* Custom metric cards with smooth animations */
    [data-testid="metric-container"] {
        background: var(--card-bg);
        border: 1px solid #404040;
        padding: 1rem;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
        overflow: hidden;
    }
    
    [data-testid="metric-container"]::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: linear-gradient(45deg, transparent, rgba(31, 119, 180, 0.05), transparent);
        opacity: 0;
        transition: opacity 0.3s ease;
    }
    
    [data-testid="metric-container"]:hover {
        transform: translateY(-4px) scale(1.02);
        box-shadow: 0 12px 25px rgba(0, 0, 0, 0.3);
        border-color: var(--primary-color);
    }
    
    [data-testid="metric-container"]:hover::before {
        opacity: 1;
    }
    
    /* Custom buttons with enhanced animations */
    .stButton > button {
        background: linear-gradient(90deg, var(--primary-color), var(--accent-color));
        color: var(--secondary-color);
        border: none;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        font-weight: 600;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
        overflow: hidden;
    }
    
    .stButton > button::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
        transition: left 0.5s;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(0, 212, 170, 0.4);
    }
    
    .stButton > button:hover::before {
        left: 100%;
    }
    
    .stButton > button:active {
        transform: translateY(0);
        transition: transform 0.1s;
    }
    
    /* Custom dataframes with animations */
    .stDataFrame {
        border-radius: 10px;
        overflow: hidden;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        transition: all 0.3s ease;
    }
    
    .stDataFrame:hover {
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
        transform: translateY(-1px);
    }
    
    /* Loading spinner */
    .stSpinner {
        text-align: center;
        color: var(--primary-color);
    }
    
    /* Alert boxes */
    .alert {
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
        border-left: 4px solid;
    }
    
    .alert-success {
        background-color: rgba(46, 160, 44, 0.1);
        border-left-color: var(--success-color);
        color: var(--success-color);
    }
    
    .alert-warning {
        background-color: rgba(255, 152, 0, 0.1);
        border-left-color: var(--warning-color);
        color: var(--warning-color);
    }
    
    .alert-danger {
        background-color: rgba(214, 39, 40, 0.1);
        border-left-color: var(--danger-color);
        color: var(--danger-color);
    }
    
    /* Enhanced Responsive design */
    @media (max-width: 1200px) {
        .main .block-container {
            padding: 1.5rem;
        }
        
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.5rem;
        }
    }
    
    @media (max-width: 768px) {
        .main .block-container {
            padding-left: 1rem;
            padding-right: 1rem;
        }
        
        [data-testid="metric-container"] {
            margin-bottom: 1rem;
        }
        
        /* Stack columns vertically on mobile */
        .element-container .stColumns {
            flex-direction: column;
        }
        
        .element-container .stColumns > div {
            width: 100% !important;
            margin-bottom: 1rem;
        }
        
        /* Adjust sidebar width */
        .css-1d391kg {
            width: 100% !important;
        }
        
        /* Make tabs scrollable on mobile */
        .stTabs [data-baseweb="tab-list"] {
            overflow-x: auto;
            white-space: nowrap;
            padding-bottom: 0.5rem;
        }
        
        .stTabs [data-baseweb="tab"] {
            min-width: 120px;
            flex-shrink: 0;
        }
        
        /* Adjust metrics for mobile */
        [data-testid="metric-container"] {
            padding: 0.75rem;
            margin: 0.5rem 0;
        }
        
        /* Make dataframes scrollable */
        .stDataFrame {
            overflow-x: auto;
        }
    }
    
    @media (max-width: 480px) {
        .main .block-container {
            padding: 0.5rem;
        }
        
        h1 {
            font-size: 1.5rem !important;
        }
        
        h2 {
            font-size: 1.25rem !important;
        }
        
        h3 {
            font-size: 1.1rem !important;
        }
        
        [data-testid="metric-container"] {
            padding: 0.5rem;
            font-size: 0.9rem;
        }
        
        .stButton > button {
            width: 100%;
            margin-bottom: 0.5rem;
        }
    }
    
    /* Tablet specific adjustments */
    @media (min-width: 769px) and (max-width: 1024px) {
        .main .block-container {
            padding: 2rem 1.5rem;
        }
        
        .element-container .stColumns > div {
            padding: 0 0.5rem;
        }
    }
    
    /* Accessibility improvements */
        /* Focus indicators */
        .stButton > button:focus,
        .stSelectbox > div > div:focus,
        .stMultiSelect > div > div:focus,
        .stSlider > div > div:focus,
        .stTabs [data-baseweb="tab"]:focus,
        .stCheckbox > label:focus-within,
        .stRadio > label:focus-within {
            outline: 2px solid var(--primary-color) !important;
            outline-offset: 2px;
            box-shadow: 0 0 0 3px rgba(31, 119, 180, 0.3) !important;
        }
        
        /* Keyboard navigation support */
        .stTabs [data-baseweb="tab"][aria-selected="true"]:focus {
            outline: 3px solid #ffffff !important;
            outline-offset: -3px;
        }
        
        /* Enhanced focus for interactive elements */
        .metric-container:focus-within {
            outline: 2px solid var(--primary-color);
            outline-offset: 2px;
            transform: translateY(-2px);
        }
        
        /* Skip navigation improvements */
        .skip-link:focus {
            position: fixed;
            top: 10px;
            left: 10px;
            z-index: 9999;
            background: var(--primary-color);
            color: white;
            padding: 12px 16px;
            text-decoration: none;
            border-radius: 4px;
            font-weight: 600;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }
        
        /* High contrast mode support */
        @media (prefers-contrast: high) {
            .metric-container {
                border: 2px solid #000;
                background: #fff;
                color: #000;
            }
            
            .stButton > button {
                border: 2px solid #000;
                background: #fff;
                color: #000;
            }
        }
        
        /* Reduced motion support */
        @media (prefers-reduced-motion: reduce) {
            * {
                animation-duration: 0.01ms !important;
                animation-iteration-count: 1 !important;
                transition-duration: 0.01ms !important;
            }
            
            .loading-spinner {
                animation: none !important;
            }
            
            .loading-bar {
                animation: none !important;
            }
        }
        
        /* Screen reader only content */
        .sr-only {
            position: absolute;
            width: 1px;
            height: 1px;
            padding: 0;
            margin: -1px;
            overflow: hidden;
            clip: rect(0, 0, 0, 0);
            white-space: nowrap;
            border: 0;
        }
        
        /* Skip link for keyboard navigation */
        .skip-link {
            position: absolute;
            top: -40px;
            left: 6px;
            background: var(--primary-color);
            color: white;
            padding: 8px;
            text-decoration: none;
            border-radius: 4px;
            z-index: 1000;
            transition: top 0.3s;
        }
        
        .skip-link:focus {
            top: 6px;
        }
        
        /* Enhanced keyboard navigation indicators */
        .stTabs [data-baseweb="tab"]:focus {
            outline: 2px solid var(--primary-color);
            outline-offset: 2px;
            background: rgba(31, 119, 180, 0.1);
        }
        
        /* ARIA live region styling */
        [aria-live] {
            position: absolute;
            left: -10000px;
            width: 1px;
            height: 1px;
            overflow: hidden;
        }
        
        /* Role-based styling */
        [role="status"] {
            position: relative;
        }
        
        [role="alert"] {
            border-left: 4px solid var(--error-color);
            padding-left: 12px;
        }
        
        /* Interactive element states */
        .stButton > button[aria-pressed="true"] {
            background: var(--success-color) !important;
            transform: scale(0.98);
        }
        
        /* Tooltip and help text styling */
        [data-tooltip]:hover::after {
            content: attr(data-tooltip);
            position: absolute;
            bottom: 100%;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(0,0,0,0.9);
            color: white;
            padding: 8px 12px;
            border-radius: 4px;
            font-size: 12px;
            white-space: nowrap;
            z-index: 1000;
        }
        
        /* Print styles */
        @media print {
            .stSidebar {
                display: none !important;
            }
            
            .main .block-container {
                max-width: 100% !important;
                padding: 0 !important;
            }
            
            .stButton {
                display: none !important;
            }
            
            /* Ensure good contrast for printing */
            .metric-container {
                background: white !important;
                color: black !important;
                border: 1px solid black !important;
            }
        }
    
    /* Custom tabs with smooth transitions */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    
    .stTabs [data-baseweb="tab"] {
        background-color: var(--card-bg);
        border-radius: 8px 8px 0 0;
        padding: 0.5rem 1rem;
        border: 1px solid #404040;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
        overflow: hidden;
    }
    
    .stTabs [data-baseweb="tab"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
        border-color: var(--primary-color);
    }
    
    .stTabs [aria-selected="true"] {
        background: linear-gradient(90deg, var(--primary-color), var(--accent-color));
        color: var(--secondary-color);
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0, 212, 170, 0.3);
    }
    
    .stTabs [data-baseweb="tab"]::before {
        content: '';
        position: absolute;
        bottom: 0;
        left: 0;
        width: 0;
        height: 2px;
        background: var(--primary-color);
        transition: width 0.3s ease;
    }
    
    .stTabs [data-baseweb="tab"]:hover::before {
        width: 100%;
    }
</style>

<script>
// Accessibility enhancements
document.addEventListener('DOMContentLoaded', function() {
    // Add keyboard navigation for tabs
    const tabs = document.querySelectorAll('.stTabs [data-baseweb="tab"]');
    tabs.forEach((tab, index) => {
        tab.setAttribute('tabindex', '0');
        tab.setAttribute('role', 'tab');
        tab.setAttribute('aria-selected', 'false');
        
        tab.addEventListener('keydown', function(e) {
            if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
                e.preventDefault();
                const nextIndex = e.key === 'ArrowRight' ? 
                    (index + 1) % tabs.length : 
                    (index - 1 + tabs.length) % tabs.length;
                tabs[nextIndex].focus();
                tabs[nextIndex].click();
            }
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                tab.click();
            }
        });
    });
    
    // Add ARIA announcements for dynamic content
    function announceToScreenReader(message) {
        const announcement = document.getElementById('status-announcements');
        if (announcement) {
            announcement.textContent = message;
            setTimeout(() => {
                announcement.textContent = '';
            }, 1000);
        }
    }
    
    // Monitor for data updates
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.type === 'childList') {
                const addedNodes = Array.from(mutation.addedNodes);
                addedNodes.forEach(node => {
                    if (node.nodeType === 1) { // Element node
                        // Announce chart updates
                        if (node.querySelector('.js-plotly-plot')) {
                            announceToScreenReader('Biểu đồ đã được cập nhật');
                        }
                        // Announce table updates
                        if (node.querySelector('[data-testid="stDataFrame"]')) {
                            announceToScreenReader('Bảng dữ liệu đã được cập nhật');
                        }
                        // Announce metric updates
                        if (node.querySelector('[data-testid="metric-container"]')) {
                            announceToScreenReader('Chỉ số đã được cập nhật');
                        }
                    }
                });
            }
        });
    });
    
    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
    
    // Add focus management for modals and overlays
    function trapFocus(element) {
        const focusableElements = element.querySelectorAll(
            'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];
        
        element.addEventListener('keydown', function(e) {
            if (e.key === 'Tab') {
                if (e.shiftKey) {
                    if (document.activeElement === firstElement) {
                        e.preventDefault();
                        lastElement.focus();
                    }
                } else {
                    if (document.activeElement === lastElement) {
                        e.preventDefault();
                        firstElement.focus();
                    }
                }
            }
            if (e.key === 'Escape') {
                element.style.display = 'none';
            }
        });
    }
    
    // Enhanced error announcements
    window.announceError = function(message) {
        announceToScreenReader('Lỗi: ' + message);
    };
    
    window.announceSuccess = function(message) {
        announceToScreenReader('Thành công: ' + message);
    };
    
    // Add tooltips for complex elements
    const complexElements = document.querySelectorAll('.metric-container, .stPlotlyChart');
    complexElements.forEach(element => {
        if (!element.getAttribute('aria-label')) {
            element.setAttribute('tabindex', '0');
            element.setAttribute('role', 'img');
            element.setAttribute('aria-label', 'Biểu đồ hoặc chỉ số tương tác');
        }
    });
});
</script>
""", unsafe_allow_html=True)


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


# Helper functions for better UX
def show_loading_message(message: str):
    """Show loading message with animated spinner."""
    loading_html = f"""
    <div class='alert alert-info' style='position: relative; overflow: hidden;'>
        <div style='display: flex; align-items: center; gap: 10px;'>
            <div class='loading-spinner'></div>
            <span>{message}</span>
        </div>
        <div class='loading-bar'></div>
    </div>
    <style>
    .loading-spinner {{
        width: 20px;
        height: 20px;
        border: 2px solid #f3f3f3;
        border-top: 2px solid #1f77b4;
        border-radius: 50%;
        animation: spin 1s linear infinite;
    }}
    
    .loading-bar {{
        position: absolute;
        bottom: 0;
        left: 0;
        height: 3px;
        background: linear-gradient(90deg, #1f77b4, #ff7f0e);
        animation: loading-progress 2s ease-in-out infinite;
    }}
    
    @keyframes spin {{
        0% {{ transform: rotate(0deg); }}
        100% {{ transform: rotate(360deg); }}
    }}
    
    @keyframes loading-progress {{
        0% {{ width: 0%; }}
        50% {{ width: 70%; }}
        100% {{ width: 100%; }}
    }}
    </style>
    """
    return st.empty().markdown(loading_html, unsafe_allow_html=True)

def show_success_message(message: str):
    """Show success message with accessibility features."""
    st.markdown(
        f'<div class="alert alert-success" role="status" aria-live="polite">✅ {message}</div>',
        unsafe_allow_html=True
    )
    # Announce to screen readers
    st.markdown(
        f'<script>if(window.announceSuccess) window.announceSuccess("{message}");</script>',
        unsafe_allow_html=True
    )

def show_warning_message(message: str):
    """Show warning message with accessibility features."""
    st.markdown(
        f'<div class="alert alert-warning" role="alert" aria-live="polite">⚠️ {message}</div>',
        unsafe_allow_html=True
    )
    # Announce to screen readers
    st.markdown(
        f'<script>if(window.announceError) window.announceError("{message}");</script>',
        unsafe_allow_html=True
    )

def show_error_message(message: str):
    """Show error message with accessibility features."""
    st.markdown(
        f'<div class="alert alert-danger" role="alert" aria-live="assertive">❌ {message}</div>',
        unsafe_allow_html=True
    )
    # Announce to screen readers
    st.markdown(
        f'<script>if(window.announceError) window.announceError("{message}");</script>',
        unsafe_allow_html=True
    )

def get_responsive_columns(num_items: int, max_cols: int = 4) -> int:
    """Get responsive number of columns based on screen size and number of items."""
    # Use session state to detect screen size (approximation)
    if 'screen_width' not in st.session_state:
        st.session_state.screen_width = 1200  # Default assumption
    
    # Adaptive column calculation
    if num_items <= 1:
        return 1
    elif num_items <= 2:
        return min(2, max_cols)
    elif num_items <= 3:
        return min(3, max_cols)
    else:
        return min(max_cols, num_items)

def create_responsive_metrics(data: dict, max_cols: int = 4):
    """Create responsive metrics layout."""
    if not data:
        return
    
    num_stocks = len(data)
    cols_per_row = get_responsive_columns(num_stocks, max_cols)
    
    # Create rows of metrics
    stock_items = list(data.items())
    for i in range(0, len(stock_items), cols_per_row):
        row_items = stock_items[i:i + cols_per_row]
        cols = st.columns(len(row_items))
        
        for j, (symbol, stock_data) in enumerate(row_items):
            with cols[j]:
                try:
                    if isinstance(stock_data, dict):
                        price = stock_data.get('close', 0)
                        change = stock_data.get('change', 0)
                        change_pct = stock_data.get('change_percent', 0)
                    else:
                        price = stock_data.iloc[-1]['close'] if not stock_data.empty else 0
                        change = stock_data.iloc[-1]['close'] - stock_data.iloc[-2]['close'] if len(stock_data) > 1 else 0
                        change_pct = (change / stock_data.iloc[-2]['close'] * 100) if len(stock_data) > 1 and stock_data.iloc[-2]['close'] != 0 else 0
                    
                    delta_color = "normal" if change >= 0 else "inverse"
                    st.metric(
                        label=symbol,
                        value=f"{price:,.0f}",
                        delta=f"{change:+.0f} ({change_pct:+.1f}%)",
                        delta_color=delta_color
                    )
                except Exception as e:
                    st.error(f"Lỗi hiển thị {symbol}: {str(e)}")

@st.cache_resource
def initialize_components():
    """Initialize and cache components with proper error handling."""
    loading_placeholder = show_loading_message("Đang khởi tạo các thành phần hệ thống...")
    
    try:
        config = load_dashboard_config()
        
        # Get credentials from environment or config
        import os
        username = os.getenv('FIINQUANT_USERNAME')
        password = os.getenv('FIINQUANT_PASSWORD')
        
        if not username or not password:
            loading_placeholder.empty()
            show_error_message("Không tìm thấy thông tin đăng nhập FiinQuant. Vui lòng kiểm tra file .env.")
            st.stop()
        
        adapter = FiinQuantAdapter(username, password)
        strategy = RSIPSAREngulfingStrategy(config)
        
        loading_placeholder.empty()
        show_success_message("Khởi tạo hệ thống thành công!")
        time.sleep(1)  # Brief pause to show success message
        
        return config, adapter, strategy
    except Exception as e:
        loading_placeholder.empty()
        show_error_message(f"Lỗi khởi tạo hệ thống: {str(e)}")
        st.stop()


@st.cache_data(ttl=30, max_entries=50, show_spinner=False)  # Optimized caching
def fetch_real_data_cached(adapter_hash: str, tickers: tuple, timestamp: int, periods: int = 100) -> Dict[str, pd.DataFrame]:
    """Cached version of data fetching to improve performance."""
    # This function will be called by the main fetch function
    # The timestamp ensures cache invalidation every 30 seconds
    return None  # Placeholder for actual implementation

def fetch_real_data(adapter: FiinQuantAdapter, tickers: List[str], periods: int = 100) -> Dict[str, pd.DataFrame]:
    """Fetch real market data from FiinQuant with optimized performance and lazy loading."""
    data = {}
    failed_tickers = []
    
    # Create progress bar
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        # Check session state cache first for better performance
        cache_timestamp = int(time.time() // 30)  # 30-second cache buckets
        
        # Login to FiinQuant
        status_text.text("Đang đăng nhập vào FiinQuant...")
        if not adapter.login():
            progress_bar.empty()
            status_text.empty()
            show_error_message("Không thể đăng nhập vào FiinQuant")
            return {}
        
        # Batch processing for better performance
        batch_size = 3  # Process 3 tickers at a time
        ticker_batches = [tickers[i:i + batch_size] for i in range(0, len(tickers), batch_size)]
        
        total_processed = 0
        for batch in ticker_batches:
            batch_data = {}
            
            for ticker in batch:
                try:
                    status_text.text(f"Đang tải dữ liệu cho {ticker}...")
                    
                    # Check session state cache first
                    cache_key = f"data_{ticker}_{cache_timestamp}_{periods}"
                    if cache_key in st.session_state:
                        batch_data[ticker] = st.session_state[cache_key]
                    else:
                        # Fetch historical data
                        df = adapter.fetch_historical_data([ticker], timeframe='15m', period=periods)
                        
                        if not df.empty:
                            # Add indicators
                            df = TechnicalIndicators.calculate_all_indicators(df)
                            batch_data[ticker] = df
                            st.session_state[cache_key] = df  # Cache in session
                        else:
                            failed_tickers.append(ticker)
                        
                except Exception as e:
                    failed_tickers.append(ticker)
                    st.warning(f"Không thể tải dữ liệu cho {ticker}: {str(e)}")
                    continue
                
                total_processed += 1
                progress_bar.progress(total_processed / len(tickers))
            
            data.update(batch_data)
            
            # Small delay between batches to prevent API rate limiting
            if len(ticker_batches) > 1:
                time.sleep(0.1)
        
        # Clear progress indicators
        progress_bar.empty()
        status_text.empty()
        
        # Show summary
        if data:
            show_success_message(f"Tải thành công dữ liệu cho {len(data)} mã cổ phiếu")
        
        if failed_tickers:
            show_warning_message(f"Không thể tải dữ liệu cho: {', '.join(failed_tickers)}")
            
        return data
        
    except Exception as e:
        progress_bar.empty()
        status_text.empty()
        show_error_message(f"Lỗi kết nối FiinQuant: {str(e)}")
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

@st.cache_data(ttl=60, max_entries=20, show_spinner=False)  # Cache charts for performance
def create_ohlc_chart_cached(df_hash: str, ticker: str, timestamp: int) -> go.Figure:
    """Cached version of chart creation for better performance."""
    # This will be called by the main chart function
    return None  # Placeholder

def create_ohlc_chart(df: pd.DataFrame, ticker: str, lazy_load: bool = True) -> go.Figure:
    """Create OHLC chart with indicators and lazy loading optimization."""
    if df.empty:
        return go.Figure()
    
    # Filter out non-trading days for continuous chart
    df = filter_trading_days(df)
    
    # Lazy loading: limit data points for initial render
    if lazy_load and len(df) > 200:
        df_display = df.tail(200)  # Show last 200 points for performance
    else:
        df_display = df
    
    # Create subplots with optimized settings
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.6, 0.2, 0.2],
        subplot_titles=[f'{ticker} - Price & PSAR', 'RSI', 'Volume']
    )
    
    # OHLC candlestick with optimized rendering
    fig.add_trace(
        go.Candlestick(
            x=df_display['timestamp'],
            open=df_display['open'],
            high=df_display['high'],
            low=df_display['low'],
            close=df_display['close'],
            name='Price',
            increasing_line_color='green',
            decreasing_line_color='red'
        ),
        row=1, col=1
    )
    
    # PSAR with conditional loading
    if 'psar' in df_display.columns and not df_display['psar'].isna().all():
        fig.add_trace(
            go.Scatter(
                x=df_display['timestamp'],
                y=df_display['psar'],
                mode='markers',
                marker=dict(size=3, color='orange'),
                name='PSAR'
            ),
            row=1, col=1
        )
    
    # RSI with conditional loading
    if 'rsi' in df_display.columns and not df_display['rsi'].isna().all():
        fig.add_trace(
            go.Scatter(
                x=df_display['timestamp'],
                y=df_display['rsi'],
                mode='lines',
                name='RSI',
                line=dict(color='purple', width=2)
            ),
            row=2, col=1
        )
        
        # RSI levels
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)
        fig.add_hline(y=50, line_dash="dash", line_color="gray", row=2, col=1)
    
    # Volume with optimized rendering
    colors = ['red' if close < open else 'green' for close, open in zip(df_display['close'], df_display['open'])]
    fig.add_trace(
        go.Bar(
            x=df_display['timestamp'],
            y=df_display['volume'],
            name='Volume',
            marker_color=colors,
            opacity=0.7
        ),
        row=3, col=1
    )
    
    # Add volume average if available
    if 'avg_volume_20' in df_display.columns and not df_display['avg_volume_20'].isna().all():
        fig.add_trace(
            go.Scatter(
                x=df_display['timestamp'],
                y=df_display['avg_volume_20'],
                mode='lines',
                name='Avg Volume',
                line=dict(color='red', dash='dash', width=1)
            ),
            row=3, col=1
        )
    
    # Update layout with performance optimizations
    fig.update_layout(
        height=700,
        showlegend=True,
        xaxis_rangeslider_visible=False,
        title_x=0.5,
        # Performance optimizations
        uirevision='constant',  # Preserve zoom/pan state
        hovermode='x unified',
        dragmode='pan'
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
    """Main dashboard function with enhanced error handling, UX, and accessibility."""
    
    # Add skip link for accessibility
    st.markdown(
        '<a href="#main-content" class="skip-link">Bỏ qua đến nội dung chính</a>',
        unsafe_allow_html=True
    )
    
    # Initialize session state
    if 'dashboard_data' not in st.session_state:
        st.session_state.dashboard_data = DashboardData()
    
    if 'last_refresh' not in st.session_state:
        st.session_state.last_refresh = datetime.now()
    
    # Initialize components with error handling
    try:
        config, adapter, strategy = initialize_components()
    except Exception as e:
        show_error_message(f"Không thể khởi tạo hệ thống: {str(e)}")
        st.stop()
    
    # Sidebar with semantic markup
    st.sidebar.markdown(
        '<h2 role="navigation" aria-label="Dashboard Settings">⚙️ Dashboard Settings</h2>',
        unsafe_allow_html=True
    )
    
    # Auto refresh toggle
    auto_refresh = st.sidebar.checkbox("Auto Refresh", value=True)
    refresh_interval = st.sidebar.slider("Refresh Interval (seconds)", 5, 60, 10)
    
    # Ticker selection
    available_tickers = ['ACB', 'VNM', 'HPG', 'VIC', 'TCB', 'FPT', 'MSN', 'VPB']
    selected_tickers = st.sidebar.multiselect(
        "Select Tickers",
        available_tickers,
        default=['ACB', 'VNM', 'HPG'],
        help="Chọn các mã cổ phiếu bạn muốn theo dõi"
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
    
    # Main content with semantic markup
    st.markdown(
        '<main id="main-content" role="main"><h1 id="main-title">📊 Real-time Trading Dashboard</h1></main>',
        unsafe_allow_html=True
    )
    st.markdown("---")
    
    # Add screen reader announcement area
    st.markdown(
        '<div aria-live="polite" aria-atomic="true" class="sr-only" id="status-announcements"></div>',
        unsafe_allow_html=True
    )
    
    # Status bar with ARIA labels
    st.markdown('<section aria-label="Market Status Overview" role="region">', unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        market_status = "🟢 Open" if datetime.now().hour < 15 else "🔴 Closed"
        st.markdown(
            f'<div role="status" aria-label="Market Status: {market_status}">',
            unsafe_allow_html=True
        )
        st.metric(
            "Market Status",
            market_status,
            ""
        )
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        active_signals = len(st.session_state.dashboard_data.get_recent_signals(1))
        st.markdown(
            f'<div role="status" aria-label="Active Signals: {active_signals} in last hour">',
            unsafe_allow_html=True
        )
        st.metric(
            "Active Signals",
            active_signals,
            "Last 1H"
        )
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col3:
        monitored_count = len(selected_tickers)
        st.markdown(
            f'<div role="status" aria-label="Monitored Tickers: {monitored_count}">',
            unsafe_allow_html=True
        )
        st.metric(
            "Monitored Tickers",
            monitored_count,
            ""
        )
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col4:
        last_update_time = st.session_state.last_refresh.strftime("%H:%M:%S")
        st.markdown(
            f'<div role="status" aria-label="Last Update: {last_update_time}">',
            unsafe_allow_html=True
        )
        st.metric(
            "Last Update",
            last_update_time,
            ""
        )
        st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown('</section>', unsafe_allow_html=True)
    
    # Email Service Status Section
    st.markdown('<section role="region" aria-label="Email Service Status">', unsafe_allow_html=True)
    st.markdown("### 📧 Email Service Status")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        try:
            from jobs.email_service import EmailService
            
            email_service = EmailService()
            
            if email_service.enabled:
                email_result = email_service.test_email_connection()
                if email_result['success']:
                    st.success("✅ Email Service: Connected")
                else:
                    st.error(f"❌ Email Service: {email_result['message']}")
            else:
                st.warning("⚠️ Email Service: Disabled")
                
        except Exception as e:
            st.error(f"❌ Email Service: Setup Required")
    
    with col2:
        if st.button("🧪 Test Email"):
            try:
                from jobs.email_service import EmailService
                
                email_service = EmailService()
                
                if email_service.enabled:
                    with st.spinner("Sending test email..."):
                        test_result = email_service.send_test_email()
                        if test_result:
                            show_success_message("Test email sent successfully!")
                        else:
                            show_error_message("Failed to send test email")
                else:
                    show_warning_message("Email service is disabled")
            except Exception as e:
                show_error_message(f"Email test failed: {str(e)}")
    

    
    st.markdown('</section>', unsafe_allow_html=True)
    
    # Validation
    if not selected_tickers:
        show_warning_message("Vui lòng chọn ít nhất một mã cổ phiếu từ sidebar.")
        st.stop()
    
    # Fetch real data from FiinQuant with error handling
    try:
        if selected_tickers:
            real_data = fetch_real_data(adapter, selected_tickers, 100)
            
            # Create responsive metrics display
            if real_data:
                st.subheader("💹 Tổng quan Giá")
                create_responsive_metrics(real_data, max_cols=4)
            
            # Generate signals from real data
            for ticker, df in real_data.items():
                try:
                    signals = strategy.analyze_ticker(ticker, df)
                    for signal in signals:
                        if (signal.confidence >= min_confidence and 
                            signal.signal_type in signal_types):
                            st.session_state.dashboard_data.add_signal(signal)
                except Exception as e:
                    show_warning_message(f"Lỗi xử lý tín hiệu cho {ticker}: {str(e)}")
    except Exception as e:
        show_error_message(f"Lỗi tải dữ liệu: {str(e)}")
        real_data = {}
    
    # Get recent signals
    recent_signals = st.session_state.dashboard_data.get_recent_signals(24)
    
    # Tabs with ARIA labels
    st.markdown('<nav role="tablist" aria-label="Dashboard Navigation">', unsafe_allow_html=True)
    tab1, tab2, tab3, tab4 = st.tabs(["📈 Charts", "🚨 Signals", "💼 Portfolio", "📊 Analytics"])
    st.markdown('</nav>', unsafe_allow_html=True)
    
    with tab1:
        st.markdown(
            '<section role="tabpanel" aria-labelledby="charts-tab"><h2 id="charts-heading">Price Charts with Indicators</h2></section>',
            unsafe_allow_html=True
        )
        
        if selected_tickers:
            # Chart selector with lazy loading option
            col1, col2 = st.columns([3, 1])
            with col1:
                chart_ticker = st.selectbox("Select Ticker for Chart", selected_tickers)
            with col2:
                lazy_load = st.checkbox("Fast Mode", value=True, help="Limit data points for faster rendering")
            
            if chart_ticker and chart_ticker in real_data:
                try:
                    df = real_data[chart_ticker]
                    
                    # Show loading message for chart
                    chart_placeholder = st.empty()
                    with chart_placeholder:
                        if lazy_load:
                            st.info("🚀 Rendering chart in fast mode...")
                        else:
                            st.info("📊 Rendering full chart...")
                    
                    # Create chart with lazy loading option
                    fig = create_ohlc_chart(df, chart_ticker, lazy_load=lazy_load)
                    
                    # Clear loading message and show chart
                    chart_placeholder.empty()
                    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': True})
                    
                    # Performance info
                    if lazy_load and len(df) > 200:
                        st.info(f"📈 Showing last 200 data points of {len(df)} total. Uncheck 'Fast Mode' to see all data.")
                    
                    # Current values
                    current_row = df.iloc[-1]
                except Exception as e:
                    show_error_message(f"Lỗi hiển thị biểu đồ {chart_ticker}: {str(e)}")
                    current_row = None
                
                if current_row is not None:
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        try:
                            st.metric(
                                "Current Price",
                                format_currency(current_row['close']),
                                f"{(current_row['close'] - current_row['open'])/current_row['open']*100:+.2f}%"
                            )
                        except Exception as e:
                            st.error(f"Lỗi hiển thị giá: {str(e)}")
                    
                    with col2:
                        try:
                            if 'rsi' in current_row:
                                st.metric(
                                    "RSI",
                                    f"{current_row['rsi']:.1f}",
                                    "Overbought" if current_row['rsi'] > 70 else "Oversold" if current_row['rsi'] < 30 else "Neutral"
                                )
                        except Exception as e:
                            st.error(f"Lỗi hiển thị RSI: {str(e)}")
                    
                    with col3:
                        try:
                            if 'psar' in current_row and 'price_vs_psar' in current_row:
                                st.metric(
                                    "PSAR Trend",
                                    "🟢 Up" if current_row['price_vs_psar'] else "🔴 Down",
                                    format_currency(current_row['psar'])
                                )
                        except Exception as e:
                            st.error(f"Lỗi hiển thị PSAR: {str(e)}")
                    
                    with col4:
                        try:
                            if 'volume_anomaly' in current_row:
                                st.metric(
                                    "Volume",
                                    "🔥 High" if current_row['volume_anomaly'] else "📊 Normal",
                                    f"{current_row['volume']:,}"
                                )
                        except Exception as e:
                            st.error(f"Lỗi hiển thị volume: {str(e)}")
    
    with tab2:
        st.markdown(
            '<section role="tabpanel" aria-labelledby="signals-tab"><h2 id="signals-heading">Recent Trading Signals</h2></section>',
            unsafe_allow_html=True
        )
        
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
            st.info("Không có tín hiệu gần đây. Đang chờ dữ liệu thị trường...")
    
    with tab3:
        st.markdown(
            '<section role="tabpanel" aria-labelledby="portfolio-tab"><h2 id="portfolio-heading">Portfolio Overview</h2></section>',
            unsafe_allow_html=True
        )
        
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
        st.markdown(
            '<section role="tabpanel" aria-labelledby="analytics-tab"><h2 id="analytics-heading">Analytics & Performance</h2></section>',
            unsafe_allow_html=True
        )
        
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
    
    # Auto refresh with error handling
    if auto_refresh:
        try:
            time.sleep(refresh_interval)
            st.rerun()
        except Exception as e:
            show_error_message(f"Lỗi tự động làm mới: {str(e)}")


if __name__ == "__main__":
    main()
