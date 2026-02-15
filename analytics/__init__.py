"""
Performance analytics for portfolio backtests.

This module provides performance metrics calculation and visualization
functions for analyzing backtest results.
"""

from .metrics import (
    calculate_returns,
    calculate_cumulative_returns,
    calculate_drawdown,
    calculate_max_drawdown,
    calculate_sharpe_ratio,
    calculate_volatility,
    calculate_cagr,
    generate_metrics_summary
)

from .visualizations import (
    plot_portfolio_comparison,
    plot_transaction_analysis,
    create_performance_table
)

__all__ = [
    'calculate_returns',
    'calculate_cumulative_returns',
    'calculate_drawdown',
    'calculate_max_drawdown',
    'calculate_sharpe_ratio',
    'calculate_volatility',
    'calculate_cagr',
    'generate_metrics_summary',
    'plot_portfolio_comparison',
    'plot_transaction_analysis',
    'create_performance_table',
]
