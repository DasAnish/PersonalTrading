"""
Performance metrics calculation for portfolio backtests.

This module provides functions to calculate common portfolio performance metrics
including returns, drawdown, Sharpe ratio, volatility, and CAGR.
"""

import pandas as pd
import numpy as np
from typing import Dict, Callable, Optional
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


def calculate_omega_ratio(
    returns: pd.Series,
    threshold: float = 0.0,
    periods_per_year: int = 252
) -> float:
    """
    Calculate Omega Ratio.

    Omega Ratio is the probability-weighted ratio of gains to losses above/below a threshold.
    Higher values indicate better risk-adjusted returns.

    Args:
        returns: Series of percentage returns
        threshold: Return threshold (default 0.0, can also use risk-free rate)
        periods_per_year: Number of periods per year (default 252 for daily)

    Returns:
        Omega Ratio (annualized)

    Example:
        >>> returns = pd.Series([0.01, 0.02, -0.01, 0.03])
        >>> calculate_omega_ratio(returns)
        2.5  # approximate
    """
    returns = returns.dropna()

    if len(returns) == 0:
        return 0.0

    # Convert threshold to period threshold
    period_threshold = threshold / periods_per_year

    # Calculate excess returns above and below threshold
    excess = returns - period_threshold

    # Separate gains and losses
    gains = excess[excess > 0].sum()
    losses = -excess[excess < 0].sum()

    if losses == 0:
        return float('inf') if gains > 0 else 0.0

    omega = gains / losses

    return omega


def calculate_returns_to_turnover_ratio(
    total_return: float,
    transactions: list,
    prices_history: pd.DataFrame = None
) -> float:
    """
    Calculate Returns to Turnover Ratio.

    Measures how much return is generated per unit of trading activity.
    Higher values indicate more efficient trading (more return per trade cost).

    Args:
        total_return: Total return as a decimal (e.g., 0.42 for 42%)
        transactions: List of Transaction objects with quantity and price
        prices_history: Optional price history for more accurate turnover calculation

    Returns:
        Returns to Turnover Ratio

    Example:
        >>> total_return = 0.42  # 42%
        >>> transactions = [...]  # list of trades
        >>> calculate_returns_to_turnover_ratio(total_return, transactions)
        0.85  # approximate
    """
    if not transactions or len(transactions) == 0:
        return 0.0

    # Calculate total turnover (sum of absolute trade values)
    total_turnover = sum(abs(t.quantity * t.price) for t in transactions)

    if total_turnover == 0:
        return 0.0

    # Returns to Turnover Ratio = Total Return / Total Turnover
    ratio = total_return / total_turnover if total_turnover > 0 else 0.0

    return ratio


def calculate_sortino_ratio(
    returns: pd.Series,
    target_return: float = 0.0,
    periods_per_year: int = 252
) -> float:
    """
    Calculate annualized Sortino ratio.

    Like Sharpe ratio but only penalizes downside volatility, making it
    more appropriate for strategies with asymmetric return distributions.

    Args:
        returns: Series of percentage returns
        target_return: Minimum acceptable return (annual, default 0.0)
        periods_per_year: Number of periods per year (default 252 for daily)

    Returns:
        Annualized Sortino ratio
    """
    returns = returns.dropna()
    if len(returns) == 0:
        return 0.0

    period_target = target_return / periods_per_year
    excess_returns = returns - period_target
    downside_returns = excess_returns[excess_returns < 0]

    if len(downside_returns) == 0:
        return float('inf') if excess_returns.mean() > 0 else 0.0

    downside_std = np.sqrt((downside_returns ** 2).mean())
    if downside_std == 0:
        return 0.0

    sortino = (excess_returns.mean() / downside_std) * np.sqrt(periods_per_year)
    return sortino


def calculate_calmar_ratio(values: pd.Series) -> float:
    """
    Calculate Calmar ratio: CAGR / |Max Drawdown|.

    Measures return per unit of maximum drawdown risk.
    Higher values indicate better risk-adjusted performance.

    Args:
        values: Series of portfolio values over time (DatetimeIndex)

    Returns:
        Calmar ratio (positive when profitable)
    """
    cagr = calculate_cagr(values)
    max_dd = calculate_max_drawdown(values)

    if max_dd == 0:
        return 0.0

    return cagr / abs(max_dd)


def calculate_information_ratio(
    returns: pd.Series,
    benchmark_returns: pd.Series,
    periods_per_year: int = 252
) -> float:
    """
    Calculate Information Ratio: excess return / tracking error.

    Measures active return per unit of active risk relative to a benchmark.

    Args:
        returns: Series of strategy returns
        benchmark_returns: Series of benchmark returns (same index)
        periods_per_year: Number of periods per year

    Returns:
        Annualized Information Ratio
    """
    active_returns = (returns - benchmark_returns).dropna()
    if len(active_returns) == 0:
        return 0.0

    tracking_err = active_returns.std()
    if tracking_err == 0:
        return 0.0

    return (active_returns.mean() / tracking_err) * np.sqrt(periods_per_year)


def calculate_tracking_error(
    returns: pd.Series,
    benchmark_returns: pd.Series,
    periods_per_year: int = 252
) -> float:
    """
    Calculate annualized tracking error vs a benchmark.

    Args:
        returns: Series of strategy returns
        benchmark_returns: Series of benchmark returns
        periods_per_year: Number of periods per year

    Returns:
        Annualized tracking error as a decimal
    """
    active_returns = (returns - benchmark_returns).dropna()
    if len(active_returns) == 0:
        return 0.0

    return active_returns.std() * np.sqrt(periods_per_year)


def calculate_var(
    returns: pd.Series,
    confidence: float = 0.95
) -> float:
    """
    Calculate historical Value at Risk.

    VaR represents the loss at the given confidence percentile.
    Example: 95% VaR of -2% means there's a 5% chance of losing more than 2% in a day.

    Args:
        returns: Series of percentage returns
        confidence: Confidence level (default 0.95)

    Returns:
        VaR as a negative decimal (e.g., -0.02 for 2% loss)
    """
    returns = returns.dropna()
    if len(returns) == 0:
        return 0.0

    return float(np.percentile(returns, (1 - confidence) * 100))


def calculate_cvar(
    returns: pd.Series,
    confidence: float = 0.95
) -> float:
    """
    Calculate Conditional Value at Risk (Expected Shortfall).

    CVaR is the average loss beyond the VaR threshold — measures tail risk.

    Args:
        returns: Series of percentage returns
        confidence: Confidence level (default 0.95)

    Returns:
        CVaR as a negative decimal
    """
    returns = returns.dropna()
    if len(returns) == 0:
        return 0.0

    var = calculate_var(returns, confidence)
    tail_losses = returns[returns <= var]

    if len(tail_losses) == 0:
        return var

    return float(tail_losses.mean())


def calculate_max_drawdown_duration(values: pd.Series) -> int:
    """
    Calculate maximum drawdown duration in days.

    Measures the longest period from a peak to full recovery.

    Args:
        values: Series of portfolio values over time

    Returns:
        Maximum drawdown duration in calendar days
    """
    if len(values) < 2:
        return 0

    running_max = values.cummax()
    in_drawdown = values < running_max

    if not in_drawdown.any():
        return 0

    max_duration = 0
    current_start = None

    for i, (date, is_dd) in enumerate(in_drawdown.items()):
        if is_dd and current_start is None:
            current_start = date
        elif not is_dd and current_start is not None:
            duration = (date - current_start).days
            max_duration = max(max_duration, duration)
            current_start = None

    # Handle ongoing drawdown at end of series
    if current_start is not None:
        duration = (values.index[-1] - current_start).days
        max_duration = max(max_duration, duration)

    return max_duration


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
    monthly = values.resample('ME').last()
    monthly_returns = monthly.pct_change().dropna()

    if monthly_returns.empty:
        return pd.DataFrame()

    # Pivot into year x month matrix
    result = pd.DataFrame({
        'year': monthly_returns.index.year,
        'month': monthly_returns.index.month,
        'return': monthly_returns.values
    })

    return result.pivot(index='year', columns='month', values='return')


def calculate_rolling_metric(
    returns: pd.Series,
    metric_fn: Callable,
    window: int = 63
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
        window_returns = returns.iloc[i - window:i]
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
    values = history['total_value']

    # Calculate returns
    returns = calculate_returns(values)

    # Calculate total return as decimal (not percentage)
    total_return_decimal = values.iloc[-1] / values.iloc[0] - 1

    # Calculate metrics
    metrics = {
        'total_return': total_return_decimal * 100,  # Percentage
        'cagr': calculate_cagr(values) * 100,  # Percentage
        'sharpe_ratio': calculate_sharpe_ratio(returns),
        'sortino_ratio': calculate_sortino_ratio(returns),
        'calmar_ratio': calculate_calmar_ratio(values),
        'max_drawdown': calculate_max_drawdown(values) * 100,  # Percentage
        'max_drawdown_duration_days': calculate_max_drawdown_duration(values),
        'volatility': calculate_volatility(returns) * 100,  # Percentage
        'var_95': calculate_var(returns, 0.95) * 100,  # Percentage
        'cvar_95': calculate_cvar(returns, 0.95) * 100,  # Percentage
        'omega_ratio': calculate_omega_ratio(returns),
        'returns_to_turnover': calculate_returns_to_turnover_ratio(total_return_decimal, transactions),
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
