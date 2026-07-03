"""
Performance metrics calculation for portfolio backtests.

This module provides functions to calculate common portfolio performance metrics
including returns, drawdown, Sharpe ratio, volatility, and CAGR.
"""

import pandas as pd
import numpy as np


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
    returns: pd.Series, risk_free_rate: float = 0.0, periods_per_year: int = 252
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
    returns: pd.Series, annualize: bool = True, periods_per_year: int = 252
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
    returns: pd.Series, threshold: float = 0.0, periods_per_year: int = 252
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
        return float("inf") if gains > 0 else 0.0

    omega = gains / losses

    return omega


def calculate_returns_to_turnover_ratio(
    total_return: float, transactions: list, prices_history: pd.DataFrame = None
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
    returns: pd.Series, target_return: float = 0.0, periods_per_year: int = 252
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
        return float("inf") if excess_returns.mean() > 0 else 0.0

    downside_std = np.sqrt((downside_returns**2).mean())
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
    returns: pd.Series, benchmark_returns: pd.Series, periods_per_year: int = 252
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
    returns: pd.Series, benchmark_returns: pd.Series, periods_per_year: int = 252
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


def calculate_var(returns: pd.Series, confidence: float = 0.95) -> float:
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


def calculate_cvar(returns: pd.Series, confidence: float = 0.95) -> float:
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
