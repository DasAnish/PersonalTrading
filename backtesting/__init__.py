"""
Backtesting framework for portfolio strategies.

This module provides components for simulating portfolio strategy execution
on historical data with transaction costs and portfolio state tracking.
"""

from .transaction import Transaction, calculate_transaction_cost
from .portfolio_state import PortfolioState
from .engine import BacktestEngine, BacktestResults

__all__ = [
    'Transaction',
    'calculate_transaction_cost',
    'PortfolioState',
    'BacktestEngine',
    'BacktestResults',
]
