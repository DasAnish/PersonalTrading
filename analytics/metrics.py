"""
Performance metrics calculation for portfolio backtests.

This module provides functions to calculate common portfolio performance metrics
including returns, drawdown, Sharpe ratio, volatility, and CAGR.
"""

import pandas as pd
import numpy as np
from typing import Dict
from backtesting.engine import BacktestResults


def calculate_returns(values: pd.Series) -> pd.Series:
    """
    Calculate percentage returns from portfolio values.

    Args:
        values: Series of portfolio values over time

    Returns:
        Series of percentage returns (same index as input)

    Example:
        >>> values = pd.Series([100, 105, 103])
        >>> returns = calculate_returns(values)
        >>> returns
        0    NaN
        1    0.05
        2   -0.019048
    """
    return values.pct_change()


def calculate_cumulative_returns(returns: pd.Series) -> pd.Series:
    """
    Calculate cumulative returns from a returns series.

    Args:
        returns: Series of percentage returns

    Returns:
        Series of cumulative returns

    Example:
        >>> returns = pd.Series([0.01, 0.02, -0.01])
        >>> cum_returns = calculate_cumulative_returns(returns)
        >>> cum_returns.iloc[-1]
        0.0198  # approximately 2% total return
    """
    return (1 + returns).cumprod() - 1


def calculate_drawdown(values: pd.Series) -> pd.Series:
    """
    Calculate drawdown series from portfolio values.

    Drawdown is the percentage decline from the previous peak.

    Args:
        values: Series of portfolio values over time

    Returns:
        Series of drawdown values (negative percentages)

    Example:
        >>> values = pd.Series([100, 110, 95, 105])
        >>> dd = calculate_drawdown(values)
        >>> dd
        0    0.0
        1    0.0
        2   -0.136364  # -13.6% from peak of 110
        3   -0.045455  # -4.5% from peak of 110
    """
    # Calculate running maximum
    running_max = values.cummax()

    # Calculate drawdown
    drawdown = (values - running_max) / running_max

    return drawdown


def calculate_max_drawdown(values: pd.Series) -> float:
    """
    Calculate maximum drawdown from portfolio values.

    Args:
        values: Series of portfolio values over time

    Returns:
        Maximum drawdown as a decimal (negative value)

    Example:
        >>> values = pd.Series([100, 110, 80, 90])
        >>> calculate_max_drawdown(values)
        -0.272727  # -27.27%
    """
    drawdown = calculate_drawdown(values)
    return drawdown.min()


def calculate_sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252
) -> float:
    """
    Calculate annualized Sharpe ratio.

    Sharpe ratio measures risk-adjusted return. Higher is better.
    Typical values: < 1 (poor), 1-2 (good), > 2 (excellent)

    Args:
        returns: Series of percentage returns
        risk_free_rate: Annual risk-free rate (default 0.0)
        periods_per_year: Number of periods per year (default 252 for daily)

    Returns:
        Annualized Sharpe ratio

    Example:
        >>> returns = pd.Series([0.001, 0.002, -0.001, 0.003])
        >>> calculate_sharpe_ratio(returns)
        1.45  # approximate
    """
    # Remove NaN values
    returns = returns.dropna()

    if len(returns) == 0:
        return 0.0

    # Convert annual risk-free rate to period rate
    period_rf_rate = risk_free_rate / periods_per_year

    # Calculate excess returns
    excess_returns = returns - period_rf_rate

    # Calculate Sharpe ratio
    mean_excess = excess_returns.mean()
    std_excess = excess_returns.std()

    if std_excess == 0:
        return 0.0

    # Annualize
    sharpe = (mean_excess / std_excess) * np.sqrt(periods_per_year)

    return sharpe


def calculate_volatility(
    returns: pd.Series,
    annualize: bool = True,
    periods_per_year: int = 252
) -> float:
    """
    Calculate volatility (standard deviation of returns).

    Args:
        returns: Series of percentage returns
        annualize: If True, annualize the volatility
        periods_per_year: Number of periods per year (default 252 for daily)

    Returns:
        Volatility as a decimal

    Example:
        >>> returns = pd.Series([0.01, -0.01, 0.02, -0.015])
        >>> calculate_volatility(returns, annualize=False)
        0.0141  # approximate
    """
    returns = returns.dropna()

    if len(returns) == 0:
        return 0.0

    vol = returns.std()

    if annualize:
        vol = vol * np.sqrt(periods_per_year)

    return vol


def calculate_cagr(values: pd.Series) -> float:
    """
    Calculate Compound Annual Growth Rate.

    CAGR represents the annualized rate of return assuming constant growth.

    Args:
        values: Series of portfolio values over time (DatetimeIndex)

    Returns:
        CAGR as a decimal

    Example:
        >>> # Portfolio grows from 100 to 150 over 2 years
        >>> dates = pd.date_range('2020-01-01', periods=505, freq='D')
        >>> values = pd.Series(np.linspace(100, 150, 505), index=dates)
        >>> calculate_cagr(values)
        0.225  # approximately 22.5% per year
    """
    if len(values) < 2:
        return 0.0

    # Calculate number of years
    start_date = values.index[0]
    end_date = values.index[-1]
    days = (end_date - start_date).days
    years = days / 365.25

    if years == 0:
        return 0.0

    # Calculate CAGR: (final_value / initial_value) ^ (1 / years) - 1
    start_value = values.iloc[0]
    end_value = values.iloc[-1]

    if start_value <= 0:
        return 0.0

    cagr = (end_value / start_value) ** (1 / years) - 1

    return cagr


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
    values = history['total_value']

    # Calculate returns
    returns = calculate_returns(values)

    # Calculate metrics
    metrics = {
        'total_return': (values.iloc[-1] / values.iloc[0] - 1) * 100,  # Percentage
        'cagr': calculate_cagr(values) * 100,  # Percentage
        'sharpe_ratio': calculate_sharpe_ratio(returns),
        'max_drawdown': calculate_max_drawdown(values) * 100,  # Percentage
        'volatility': calculate_volatility(returns) * 100,  # Percentage
        'total_transactions': len(transactions),
        'total_transaction_costs': sum(t.total_cost for t in transactions),
        'final_value': values.iloc[-1],
        'initial_value': values.iloc[0],
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
    position_cols = [col for col in history.columns if col.endswith('_value')]

    if not position_cols:
        return pd.DataFrame()

    # Extract symbol names from column names (remove _value suffix)
    symbols = [col.replace('_value', '') for col in position_cols]

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

    return metrics
