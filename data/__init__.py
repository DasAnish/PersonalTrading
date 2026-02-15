"""
Data management utilities for backtesting.

This module provides data caching and preprocessing functions to prepare
historical market data for backtesting.
"""

from .cache import HistoricalDataCache
from .preprocessing import (
    align_dataframes,
    validate_data_quality,
    resample_to_frequency,
    handle_missing_data,
    calculate_correlation_matrix
)

__all__ = [
    'HistoricalDataCache',
    'align_dataframes',
    'validate_data_quality',
    'resample_to_frequency',
    'handle_missing_data',
    'calculate_correlation_matrix',
]
