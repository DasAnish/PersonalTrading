"""
Aggregate and derived performance metrics for portfolio backtests.

These functions build on the primitive metric calculations in
``analytics/metrics.py`` (returns, Sharpe, drawdown, etc.) to produce
higher-level summaries: monthly return matrices, rolling metric series,
a full metrics summary dict, and per-asset return attribution.

Split out of ``analytics/metrics.py`` to keep that module under the
project's 600-line file-size limit; all four functions remain importable
from the top-level ``analytics`` package.
"""

import pandas as pd
from typing import Dict, Callable
from backtesting.engine import BacktestResults
from .metrics import (
    calculate_returns,
    calculate_cagr,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    calculate_calmar_ratio,
    calculate_max_drawdown,
    calculate_max_drawdown_duration,
    calculate_volatility,
    calculate_var,
    calculate_cvar,
    calculate_omega_ratio,
    calculate_returns_to_turnover_ratio,
)


def calculate_monthly_returns(values: pd.Series) -> pd.DataFrame:
    """
    Calculate monthly returns matrix.

    Args:
        values: Series of portfolio values with DatetimeIndex

    Returns:
        DataFrame with rows=years, columns=months (1-12), values=monthly returns
    """
    if len(values) < 2:
        return pd.DataFrame()

    # Resample to month-end and calculate returns
    monthly = values.resample("ME").last()
    monthly_returns = monthly.pct_change().dropna()

    if monthly_returns.empty:
        return pd.DataFrame()

    # Pivot into year x month matrix
    result = pd.DataFrame(
        {
            "year": monthly_returns.index.year,
            "month": monthly_returns.index.month,
            "return": monthly_returns.values,
        }
    )

    return result.pivot(index="year", columns="month", values="return")


def calculate_rolling_metric(
    returns: pd.Series, metric_fn: Callable, window: int = 63
) -> pd.Series:
    """
    Calculate a rolling metric over a returns series.

    Args:
        returns: Series of percentage returns
        metric_fn: Function that takes a returns Series and returns a float
                   (e.g., calculate_sharpe_ratio, calculate_volatility)
        window: Rolling window size in periods (default 63 = ~3 months)

    Returns:
        Series of rolling metric values
    """
    returns = returns.dropna()
    if len(returns) < window:
        return pd.Series(dtype=float)

    results = {}
    for i in range(window, len(returns) + 1):
        window_returns = returns.iloc[i - window : i]
        results[returns.index[i - 1]] = metric_fn(window_returns)

    return pd.Series(results)


def generate_metrics_summary(backtest_results: BacktestResults) -> Dict[str, float]:
    """
    Generate comprehensive performance metrics summary.

    Args:
        backtest_results: BacktestResults object from backtest

    Returns:
        Dictionary of performance metrics

    Metrics included:
        - total_return: Total return as percentage
        - cagr: Compound annual growth rate
        - sharpe_ratio: Annualized Sharpe ratio
        - max_drawdown: Maximum drawdown
        - volatility: Annualized volatility
        - omega_ratio: Omega Ratio (probability-weighted gain/loss ratio)
        - returns_to_turnover: Returns to Turnover Ratio
        - total_transactions: Number of transactions executed
        - total_transaction_costs: Total costs paid

    Example:
        >>> metrics = generate_metrics_summary(results)
        >>> metrics['sharpe_ratio']
        1.25
    """
    history = backtest_results.portfolio_history
    transactions = backtest_results.transactions

    # Extract portfolio values
    values = history["total_value"]

    # Calculate returns
    returns = calculate_returns(values)

    # Calculate total return as decimal (not percentage)
    total_return_decimal = values.iloc[-1] / values.iloc[0] - 1

    # Calculate metrics
    metrics = {
        "total_return": total_return_decimal * 100,  # Percentage
        "cagr": calculate_cagr(values) * 100,  # Percentage
        "sharpe_ratio": calculate_sharpe_ratio(returns),
        "sortino_ratio": calculate_sortino_ratio(returns),
        "calmar_ratio": calculate_calmar_ratio(values),
        "max_drawdown": calculate_max_drawdown(values) * 100,  # Percentage
        "max_drawdown_duration_days": calculate_max_drawdown_duration(values),
        "volatility": calculate_volatility(returns) * 100,  # Percentage
        "var_95": calculate_var(returns, 0.95) * 100,  # Percentage
        "cvar_95": calculate_cvar(returns, 0.95) * 100,  # Percentage
        "omega_ratio": calculate_omega_ratio(returns),
        "returns_to_turnover": calculate_returns_to_turnover_ratio(
            total_return_decimal, transactions
        ),
        "total_transactions": len(transactions),
        "total_transaction_costs": sum(t.total_cost for t in transactions),
        "final_value": values.iloc[-1],
        "initial_value": values.iloc[0],
    }

    # Store in backtest results
    backtest_results.metrics = metrics


def calculate_return_attribution(history: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate return attribution by asset over time.

    Args:
        history: Portfolio history DataFrame with position values (columns: SYMBOL_value)

    Returns:
        DataFrame with cumulative return for each asset over time
    """
    # Extract position value columns (format: SYMBOL_value)
    position_cols = [col for col in history.columns if col.endswith("_value")]

    if not position_cols:
        return pd.DataFrame()

    # Extract symbol names from column names (remove _value suffix)
    symbols = [col.replace("_value", "") for col in position_cols]

    # Get position values
    positions = history[position_cols].copy()
    positions.columns = symbols

    # Fill NaN values with 0 (no position yet)
    positions = positions.fillna(0)

    # Calculate cumulative return for each asset
    # Start with initial value of 0, then calculate how much each asset gained/lost
    attribution = positions.copy()

    # Convert to cumulative change from start (each column - its first non-zero value)
    for col in attribution.columns:
        first_nonzero_idx = (attribution[col] != 0).idxmax()
        if attribution[col].iloc[0] == 0 and first_nonzero_idx in attribution.index:
            first_nonzero_value = attribution[col].loc[first_nonzero_idx]
            if first_nonzero_value > 0:
                # Calculate return contribution: current value - initial invested value
                attribution[col] = attribution[col] - first_nonzero_value
        else:
            # No position, set to 0
            attribution[col] = attribution[col] - attribution[col].iloc[0]

    return attribution
