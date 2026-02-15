"""
Data preprocessing utilities for backtesting.

This module provides functions to align, clean, and validate historical
price data from multiple symbols.
"""

import pandas as pd
import numpy as np
from typing import Dict
import logging

logger = logging.getLogger(__name__)


def align_dataframes(data_dict: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Align multiple DataFrames into a single price matrix.

    Takes a dictionary of DataFrames (one per symbol) and creates a unified
    DataFrame with symbols as columns and dates as index.

    Args:
        data_dict: Dict mapping symbol to DataFrame
                  Each DataFrame should have 'close' column and datetime index

    Returns:
        DataFrame with:
        - Index: dates (intersection of all available dates)
        - Columns: symbols
        - Values: close prices

    Example:
        >>> data = {
        ...     'VUSA': vusa_df,  # Has columns: open, high, low, close, volume
        ...     'SSLN': ssln_df
        ... }
        >>> prices = align_dataframes(data)
        >>> prices.columns
        Index(['VUSA', 'SSLN'], dtype='object')
    """
    if not data_dict:
        return pd.DataFrame()

    # Extract close prices from each DataFrame
    price_series = {}

    for symbol, df in data_dict.items():
        if df.empty:
            logger.warning(f"Empty DataFrame for {symbol}, skipping")
            continue

        if 'close' not in df.columns:
            logger.error(f"No 'close' column in {symbol} DataFrame")
            continue

        # Extract close prices
        close_prices = df['close'].copy()
        close_prices.name = symbol

        price_series[symbol] = close_prices

    if not price_series:
        logger.error("No valid price data found")
        return pd.DataFrame()

    # Combine into single DataFrame
    prices = pd.DataFrame(price_series)

    # Log date range for each symbol
    for symbol in prices.columns:
        symbol_data = prices[symbol].dropna()
        if len(symbol_data) > 0:
            logger.info(
                f"{symbol}: {len(symbol_data)} days, "
                f"{symbol_data.index[0].date()} to {symbol_data.index[-1].date()}"
            )

    # Forward fill missing values (max 3 days)
    prices = prices.ffill(limit=3)

    # Drop any remaining NaN rows
    before_drop = len(prices)
    prices = prices.dropna()
    after_drop = len(prices)

    if before_drop > after_drop:
        logger.info(f"Dropped {before_drop - after_drop} rows with missing data")

    # Log final aligned date range
    if not prices.empty:
        logger.info(
            f"Aligned data: {len(prices)} days, "
            f"{prices.index[0].date()} to {prices.index[-1].date()}"
        )

    return prices


def validate_data_quality(
    prices: pd.DataFrame,
    min_data_points: int = 252,
    max_nan_pct: float = 0.05
) -> bool:
    """
    Validate data quality for backtesting.

    Checks:
    1. Sufficient data points
    2. Not too many NaN values
    3. No negative prices
    4. No excessive price jumps (>50% in one day)

    Args:
        prices: DataFrame with columns=symbols, index=dates, values=prices
        min_data_points: Minimum number of data points required (default 252 = 1 year)
        max_nan_pct: Maximum percentage of NaN values allowed (default 0.05 = 5%)

    Returns:
        True if data quality is acceptable, False otherwise

    Example:
        >>> if validate_data_quality(prices):
        ...     print("Data quality OK")
        ... else:
        ...     print("Data quality issues")
    """
    if prices.empty:
        logger.error("Data validation failed: empty DataFrame")
        return False

    # Check sufficient data points
    if len(prices) < min_data_points:
        logger.error(
            f"Insufficient data points: {len(prices)} < {min_data_points} required"
        )
        return False

    # Check NaN percentage
    nan_pct = prices.isnull().sum().sum() / (len(prices) * len(prices.columns))
    if nan_pct > max_nan_pct:
        logger.error(
            f"Too many NaN values: {nan_pct*100:.2f}% > {max_nan_pct*100:.2f}% threshold"
        )
        return False

    # Check for negative prices
    if (prices < 0).any().any():
        logger.error("Negative prices detected")
        return False

    # Check for zero prices
    if (prices == 0).any().any():
        logger.warning("Zero prices detected")

    # Check for excessive price jumps (>50% in one day)
    returns = prices.pct_change()
    if (abs(returns) > 0.5).any().any():
        logger.warning("Large price jumps detected (>50% in one day)")

    logger.info("Data quality validation passed")
    return True


def resample_to_frequency(
    prices: pd.DataFrame,
    frequency: str = '1D'
) -> pd.DataFrame:
    """
    Resample price data to specified frequency.

    Useful for converting daily data to weekly or monthly data.

    Args:
        prices: DataFrame with datetime index
        frequency: Pandas frequency string ('1D', '1W', '1M', etc.)

    Returns:
        Resampled DataFrame (last price of period)

    Example:
        >>> weekly_prices = resample_to_frequency(daily_prices, '1W')
    """
    if prices.empty:
        return prices

    # Resample to last price of period
    resampled = prices.resample(frequency).last()

    # Forward fill any missing values
    resampled = resampled.ffill()

    logger.info(f"Resampled from {len(prices)} to {len(resampled)} periods")

    return resampled


def handle_missing_data(
    prices: pd.DataFrame,
    method: str = 'ffill',
    limit: int = 3
) -> pd.DataFrame:
    """
    Handle missing data in price DataFrame.

    Args:
        prices: DataFrame with prices
        method: Fill method ('ffill', 'bfill', 'interpolate', 'drop')
        limit: Maximum number of consecutive NaN values to fill

    Returns:
        DataFrame with missing data handled

    Example:
        >>> clean_prices = handle_missing_data(prices, method='ffill', limit=3)
    """
    if prices.empty:
        return prices

    original_len = len(prices)

    if method == 'ffill':
        prices = prices.ffill(limit=limit)
    elif method == 'bfill':
        prices = prices.bfill(limit=limit)
    elif method == 'interpolate':
        prices = prices.interpolate(method='linear', limit=limit)
    elif method == 'drop':
        prices = prices.dropna()
    else:
        logger.warning(f"Unknown method '{method}', using ffill")
        prices = prices.ffill(limit=limit)

    # Drop any remaining NaN
    prices = prices.dropna()

    if len(prices) < original_len:
        logger.info(f"Filled/dropped {original_len - len(prices)} rows with missing data")

    return prices


def calculate_correlation_matrix(prices: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate correlation matrix from prices.

    Args:
        prices: DataFrame with columns=symbols, index=dates, values=prices

    Returns:
        Correlation matrix DataFrame

    Example:
        >>> corr = calculate_correlation_matrix(prices)
        >>> print(corr)
              VUSA  SSLN  SGLN  IWRD
        VUSA  1.00  0.85  0.45  0.92
        SSLN  0.85  1.00  0.35  0.88
        ...
    """
    if prices.empty:
        return pd.DataFrame()

    # Calculate returns
    returns = prices.pct_change().dropna()

    # Calculate correlation
    corr = returns.corr()

    return corr
