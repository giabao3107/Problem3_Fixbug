"""
Risk Management Module
Handles position sizing, portfolio limits, and signal filtering.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import logging


@dataclass
class RiskMetrics:
    """Risk metrics for portfolio monitoring."""
    total_portfolio_value: float
    total_exposure: float
    daily_pnl: float
    daily_drawdown: float
    active_positions_count: int
    risk_limit_usage: float  # Percentage of risk limits used
    max_position_size: float
    diversification_score: float


class RiskManager:
    """
    Portfolio risk management with position sizing and exposure limits.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize risk manager.
        
        Args:
            config: Risk management configuration
        """
        self.config = config
        
        # Risk parameters
        self.take_profit = config.get('take_profit', 0.15)  # 15%
        self.stop_loss = config.get('stop_loss', 0.08)      # 8%
        self.trailing_take_profit = config.get('trailing_take_profit', 0.09)  # 9%
        self.trailing_stop = config.get('trailing_stop', 0.03)  # 3%
        self.position_size = config.get('position_size', 0.02)  # 2% per trade
        self.max_positions = config.get('max_positions', 10)
        self.max_daily_loss = config.get('max_daily_loss', 0.05)  # 5%
        
        # State tracking
        self.daily_trades = {}  # Date -> count
        self.daily_pnl = {}     # Date -> PnL
        self.position_history = []
        
        # Circuit breaker
        self.circuit_breaker_active = False
        self.circuit_breaker_until = None
        
        self.logger = logging.getLogger(__name__)
    
    def calculate_position_size(self, ticker: str, entry_price: float,
                              stop_loss_price: float,
                              portfolio_value: float) -> int:
        """
        Calculate position size based on risk management rules.
        
        Args:
            ticker: Stock symbol
            entry_price: Entry price per share
            stop_loss_price: Stop loss price per share
            portfolio_value: Current portfolio value
            
        Returns:
            int: Number of shares to buy (0 if risk too high)
        """
        if entry_price <= 0 or stop_loss_price <= 0 or portfolio_value <= 0:
            return 0
        
        # Calculate risk per share
        risk_per_share = abs(entry_price - stop_loss_price)
        
        if risk_per_share <= 0:
            return 0
        
        # Calculate maximum risk amount
        max_risk_amount = portfolio_value * self.position_size
        
        # Calculate position size
        position_size = int(max_risk_amount / risk_per_share)
        
        # Apply additional constraints
        max_position_value = portfolio_value * 0.1  # Max 10% in single position
        max_shares_by_value = int(max_position_value / entry_price)
        
        position_size = min(position_size, max_shares_by_value)
        
        # Minimum position size check
        min_shares = max(1, int(1000 / entry_price))  # At least 1000 VND worth
        
        return max(0, min(position_size, 999999)) if position_size >= min_shares else 0
    
    def check_position_limits(self, ticker: str, current_positions: Dict) -> bool:
        """
        Check if adding a new position would violate limits.
        
        Args:
            ticker: Stock symbol to check
            current_positions: Dict of current positions
            
        Returns:
            bool: True if position can be added
        """
        # Check maximum concurrent positions
        active_count = len([p for p in current_positions.values() 
                          if p.position_status != 'none'])
        
        if active_count >= self.max_positions:
            self.logger.warning(f"Max positions limit reached: {active_count}/{self.max_positions}")
            return False
        
        # Check if already have position in this ticker
        if ticker in current_positions and current_positions[ticker].position_status != 'none':
            self.logger.warning(f"Already have position in {ticker}")
            return False
        
        # Check daily trade limits (optional)
        today = datetime.now().date()
        daily_count = self.daily_trades.get(today, 0)
        max_daily_trades = 20  # Configurable limit
        
        if daily_count >= max_daily_trades:
            self.logger.warning(f"Daily trade limit reached: {daily_count}/{max_daily_trades}")
            return False
        
        # Check circuit breaker
        if self.circuit_breaker_active:
            if datetime.now() < self.circuit_breaker_until:
                self.logger.warning("Circuit breaker active - no new positions allowed")
                return False
            else:
                self.circuit_breaker_active = False
                self.circuit_breaker_until = None
        
        return True
    
    def check_daily_loss_limit(self, current_pnl: float, portfolio_value: float) -> bool:
        """
        Check if daily loss limit has been exceeded.
        
        Args:
            current_pnl: Current day's P&L
            portfolio_value: Total portfolio value
            
        Returns:
            bool: True if within limits, False if exceeded
        """
        max_loss = portfolio_value * self.max_daily_loss
        
        if current_pnl < -max_loss:
            self.logger.error(f"Daily loss limit exceeded: {current_pnl:.0f} < -{max_loss:.0f}")
            self._activate_circuit_breaker()
            return False
        
        return True
    
    def _activate_circuit_breaker(self, duration_hours: int = 2):
        """
        Activate circuit breaker to prevent further trading.
        
        Args:
            duration_hours: How long to keep circuit breaker active
        """
        self.circuit_breaker_active = True
        self.circuit_breaker_until = datetime.now() + timedelta(hours=duration_hours)
        self.logger.critical(f"Circuit breaker activated until {self.circuit_breaker_until}")
    
    def filter_signals(self, ticker: str, signals: List, 
                      current_positions: Dict) -> List:
        """
        Filter trading signals based on risk management rules.
        
        Args:
            ticker: Stock symbol
            signals: List of trading signals
            current_positions: Current position states
            
        Returns:
            List: Filtered signals
        """
        if not signals:
            return []
        
        filtered_signals = []
        
        for signal in signals:
            # Always allow sell and risk warning signals
            if signal.signal_type in ['sell', 'risk_warning']:
                filtered_signals.append(signal)
                continue
            
            # For buy signals, check limits
            if signal.signal_type == 'buy':
                if self.check_position_limits(ticker, current_positions):
                    # Additional confidence filter for high-risk periods
                    min_confidence = 0.7 if self._is_high_risk_period() else 0.6
                    
                    if signal.confidence >= min_confidence:
                        filtered_signals.append(signal)
                    else:
                        self.logger.debug(f"Signal filtered out due to low confidence: {signal.confidence}")
                else:
                    self.logger.debug(f"Signal filtered out due to position limits")
        
        return filtered_signals
    
    def _is_high_risk_period(self) -> bool:
        """
        Determine if current period has elevated risk.
        
        Returns:
            bool: True if high risk period
        """
        # Check recent P&L performance
        today = datetime.now().date()
        recent_days = [today - timedelta(days=i) for i in range(3)]
        
        recent_losses = sum([
            self.daily_pnl.get(day, 0) for day in recent_days
            if self.daily_pnl.get(day, 0) < 0
        ])
        
        # If lost more than 2% in recent days, consider high risk
        return recent_losses < -0.02  # 2% threshold
    
    def update_daily_metrics(self, date: datetime, pnl: float, trade_count: int = 0):
        """
        Update daily tracking metrics.
        
        Args:
            date: Date to update
            pnl: Daily P&L
            trade_count: Number of trades
        """
        day_key = date.date()
        
        self.daily_pnl[day_key] = pnl
        
        if trade_count > 0:
            self.daily_trades[day_key] = self.daily_trades.get(day_key, 0) + trade_count
        
        # Clean up old data (keep last 30 days)
        cutoff_date = day_key - timedelta(days=30)
        
        self.daily_pnl = {k: v for k, v in self.daily_pnl.items() if k >= cutoff_date}
        self.daily_trades = {k: v for k, v in self.daily_trades.items() if k >= cutoff_date}
    
    def calculate_risk_metrics(self, current_positions: Dict, 
                             portfolio_value: float) -> RiskMetrics:
        """
        Calculate comprehensive risk metrics.
        
        Args:
            current_positions: Current position states
            portfolio_value: Total portfolio value
            
        Returns:
            RiskMetrics: Risk metrics object
        """
        active_positions = {k: v for k, v in current_positions.items() 
                          if v.position_status != 'none'}
        
        # Calculate total exposure
        total_exposure = 0.0
        position_values = []
        
        for ticker, state in active_positions.items():
            if state.entry_price and state.current_price:
                position_value = abs(state.current_price - state.entry_price) / state.entry_price
                total_exposure += position_value
                position_values.append(position_value)
        
        # Daily P&L
        today = datetime.now().date()
        daily_pnl = self.daily_pnl.get(today, 0.0)
        daily_drawdown = min(0, daily_pnl / portfolio_value) if portfolio_value > 0 else 0
        
        # Risk limit usage
        risk_limit_usage = len(active_positions) / self.max_positions
        
        # Maximum position size
        max_position_size = max(position_values) if position_values else 0.0
        
        # Diversification score (higher is better)
        diversification_score = len(active_positions) / self.max_positions if active_positions else 0
        
        return RiskMetrics(
            total_portfolio_value=portfolio_value,
            total_exposure=total_exposure,
            daily_pnl=daily_pnl,
            daily_drawdown=daily_drawdown,
            active_positions_count=len(active_positions),
            risk_limit_usage=risk_limit_usage,
            max_position_size=max_position_size,
            diversification_score=diversification_score
        )
    
    def get_risk_warnings(self, risk_metrics: RiskMetrics) -> List[str]:
        """
        Generate risk warning messages.
        
        Args:
            risk_metrics: Current risk metrics
            
        Returns:
            List[str]: List of warning messages
        """
        warnings = []
        
        # High exposure warning
        if risk_metrics.total_exposure > 0.8:  # 80% of portfolio
            warnings.append(f"High total exposure: {risk_metrics.total_exposure:.1%}")
        
        # Daily loss warning
        if risk_metrics.daily_drawdown < -0.03:  # -3%
            warnings.append(f"Significant daily loss: {risk_metrics.daily_drawdown:.1%}")
        
        # Position concentration warning
        if risk_metrics.max_position_size > 0.15:  # 15% in single position
            warnings.append(f"Large position concentration: {risk_metrics.max_position_size:.1%}")
        
        # Position limit warning
        if risk_metrics.risk_limit_usage > 0.8:  # 80% of position limit
            warnings.append(f"Near position limit: {risk_metrics.active_positions_count}/{self.max_positions}")
        
        # Circuit breaker warning
        if self.circuit_breaker_active:
            warnings.append(f"Circuit breaker active until {self.circuit_breaker_until}")
        
        return warnings
    
    def should_scale_out(self, ticker: str, current_state, 
                        unrealized_pnl_percent: float) -> bool:
        """
        Determine if position should be partially closed (scale out).
        
        Args:
            ticker: Stock symbol
            current_state: Current position state
            unrealized_pnl_percent: Current unrealized P&L percentage
            
        Returns:
            bool: True if should scale out
        """
        # Scale out at certain profit levels to lock in gains
        scale_out_levels = [0.10, 0.20, 0.30]  # 10%, 20%, 30% profit
        
        for level in scale_out_levels:
            if unrealized_pnl_percent >= level:
                # Check if we haven't already scaled out at this level
                # This would require additional state tracking
                return True
        
        return False
    
    def calculate_optimal_stop_loss(self, entry_price: float, 
                                  volatility: float) -> float:
        """
        Calculate adaptive stop loss based on volatility.
        
        Args:
            entry_price: Entry price
            volatility: Recent volatility measure
            
        Returns:
            float: Optimal stop loss price
        """
        # Base stop loss
        base_sl_percent = self.stop_loss
        
        # Adjust for volatility
        # Higher volatility = wider stops to avoid whipsaws
        volatility_adjustment = min(0.05, volatility * 2)  # Max 5% adjustment
        
        adjusted_sl_percent = base_sl_percent + volatility_adjustment
        
        return entry_price * (1 - adjusted_sl_percent)
    
    def get_portfolio_summary(self, current_positions: Dict, 
                            portfolio_value: float) -> Dict[str, Any]:
        """
        Generate portfolio summary for reporting.
        
        Args:
            current_positions: Current position states
            portfolio_value: Total portfolio value
            
        Returns:
            Dict: Portfolio summary
        """
        risk_metrics = self.calculate_risk_metrics(current_positions, portfolio_value)
        warnings = self.get_risk_warnings(risk_metrics)
        
        active_positions = {k: v for k, v in current_positions.items() 
                          if v.position_status != 'none'}
        
        # Calculate individual position P&L
        position_pnls = {}
        total_unrealized = 0.0
        
        for ticker, state in active_positions.items():
            if state.entry_price and state.current_price:
                pnl = (state.current_price - state.entry_price) / state.entry_price
                position_pnls[ticker] = pnl
                total_unrealized += pnl
        
        summary = {
            'portfolio_value': portfolio_value,
            'active_positions': len(active_positions),
            'max_positions': self.max_positions,
            'position_utilization': f"{len(active_positions)}/{self.max_positions}",
            'total_unrealized_pnl': total_unrealized,
            'daily_pnl': risk_metrics.daily_pnl,
            'daily_drawdown_percent': risk_metrics.daily_drawdown * 100,
            'risk_warnings': warnings,
            'circuit_breaker_active': self.circuit_breaker_active,
            'position_details': position_pnls,
            'risk_limit_usage_percent': risk_metrics.risk_limit_usage * 100
        }
        
        return summary
