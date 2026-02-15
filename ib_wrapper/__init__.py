"""
Interactive Brokers Python Wrapper.

A modern, asyncio-based Python wrapper for the Interactive Brokers API
using ib_insync. Provides simple access to market data, positions,
and real-time portfolio updates.

Example usage:
    >>> from ib_wrapper import IBClient, Config
    >>> async with IBClient() as client:
    ...     bars = await client.get_historical_bars("AAPL", "1 D", "1 min")
    ...     positions = await client.get_positions()
"""

from .client import IBClient
from .config import Config
from .models import (
    Position,
    AccountSummary,
    HistoricalBar,
    PortfolioUpdate,
    ConnectionConfig,
    PnLUpdate,
    PnLSingleUpdate
)
from .exceptions import (
    IBWrapperException,
    ConnectionException,
    AuthenticationException,
    DataRequestException,
    RateLimitException,
    InvalidContractException,
    PortfolioException,
    ConfigurationException
)

__version__ = "0.1.0"
__author__ = "DasAnish"

__all__ = [
    # Main client
    "IBClient",
    "Config",
    # Models
    "Position",
    "AccountSummary",
    "HistoricalBar",
    "PortfolioUpdate",
    "ConnectionConfig",
    "PnLUpdate",
    "PnLSingleUpdate",
    # Exceptions
    "IBWrapperException",
    "ConnectionException",
    "AuthenticationException",
    "DataRequestException",
    "RateLimitException",
    "InvalidContractException",
    "PortfolioException",
    "ConfigurationException",
]
