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
    calculate_sortino_ratio,
    calculate_calmar_ratio,
    calculate_information_ratio,
    calculate_tracking_error,
    calculate_var,
    calculate_cvar,
    calculate_max_drawdown_duration,
    calculate_monthly_returns,
    calculate_rolling_metric,
    calculate_volatility,
    calculate_cagr,
    calculate_omega_ratio,
    calculate_returns_to_turnover_ratio,
    generate_metrics_summary
)

from .visualizations import (
    plot_portfolio_comparison,
    plot_transaction_analysis,
    create_performance_table
)

from .overfitting import (
    calculate_deflated_sharpe_ratio,
    calculate_pbo,
    run_overfitting_analysis,
    overfitting_analysis_to_dict,
    DSRResult,
    PBOResult,
    OverfittingAnalysis,
)

__all__ = [
    'calculate_returns',
    'calculate_cumulative_returns',
    'calculate_drawdown',
    'calculate_max_drawdown',
    'calculate_sharpe_ratio',
    'calculate_sortino_ratio',
    'calculate_calmar_ratio',
    'calculate_information_ratio',
    'calculate_tracking_error',
    'calculate_var',
    'calculate_cvar',
    'calculate_max_drawdown_duration',
    'calculate_monthly_returns',
    'calculate_rolling_metric',
    'calculate_volatility',
    'calculate_cagr',
    'calculate_omega_ratio',
    'calculate_returns_to_turnover_ratio',
    'generate_metrics_summary',
    'plot_portfolio_comparison',
    'plot_transaction_analysis',
    'create_performance_table',
    'calculate_deflated_sharpe_ratio',
    'calculate_pbo',
    'run_overfitting_analysis',
    'overfitting_analysis_to_dict',
    'DSRResult',
    'PBOResult',
    'OverfittingAnalysis',
]
