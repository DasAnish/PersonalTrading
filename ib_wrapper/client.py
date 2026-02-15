"""
Main client wrapper for Interactive Brokers API.

This module provides a unified interface to all IB operations,
orchestrating connection, market data, and portfolio services.
"""

import logging
from typing import List, Dict, Optional, Callable
from datetime import datetime

import pandas as pd

from .connection import IBConnectionManager
from .market_data import MarketDataService
from .portfolio import PortfolioService
from .config import Config
from .models import Position, PortfolioUpdate, PnLUpdate, PnLSingleUpdate
from .utils import setup_logging

logger = logging.getLogger(__name__)


class IBClient:
    """
    Main client wrapper providing unified access to IB functionality.

    This class orchestrates all sub-components and provides a simple,
    unified API for working with Interactive Brokers.

    Examples:
        >>> # Using async context manager
        >>> async with IBClient(config) as client:
        ...     bars = await client.get_historical_bars("AAPL", "1 D", "1 min")
        ...     positions = await client.get_positions()

        >>> # Manual connection management
        >>> client = IBClient(config)
        >>> await client.connect()
        >>> bars = await client.get_historical_bars("AAPL", "1 D", "1 min")
        >>> await client.disconnect()
    """

    def __init__(self, config: Optional[Config] = None):
        """
        Initialize IB client.

        Args:
            config: Configuration object (optional, creates default if not provided)
        """
        # Load configuration
        self.config = config if config else Config()

        # Setup logging
        log_config = self.config.get('logging', {})
        setup_logging(
            level=log_config.get('level', 'INFO'),
            log_file=log_config.get('file'),
            console=log_config.get('console', True)
        )

        # Initialize connection manager
        conn_config = self.config.get_connection_config()
        self.connection = IBConnectionManager(conn_config)

        # Initialize services (will use connection's ib instance)
        market_data_config = self.config.get('market_data', {})
        self.market_data = MarketDataService(
            ib=self.connection.ib,
            rate_limit_requests=market_data_config.get('rate_limit_requests', 50),
            rate_limit_window=market_data_config.get('rate_limit_window', 600)
        )

        self.portfolio = PortfolioService(ib=self.connection.ib)

        logger.info("IBClient initialized")

    async def connect(self) -> bool:
        """
        Connect to IB Gateway/TWS.

        Returns:
            True if connection successful

        Examples:
            >>> await client.connect()
        """
        return await self.connection.connect()

    def disconnect(self):
        """
        Disconnect from IB Gateway/TWS.

        Examples:
            >>> client.disconnect()
        """
        # Unsubscribe from all updates
        self.portfolio.unsubscribe_portfolio_updates()

        # Disconnect
        self.connection.disconnect()

    def is_connected(self) -> bool:
        """
        Check if connected to IB.

        Returns:
            True if connected, False otherwise

        Examples:
            >>> if client.is_connected():
            ...     print("Connected!")
        """
        return self.connection.is_connected()

    # Market Data Methods

    async def get_historical_bars(
        self,
        symbol: str,
        duration: str = "1 D",
        bar_size: str = "1 min",
        **kwargs
    ) -> pd.DataFrame:
        """
        Fetch historical bars for a symbol.

        Args:
            symbol: Ticker symbol
            duration: How far back to fetch (e.g., '1 D', '1 W', '1 M')
            bar_size: Bar size (e.g., '1 min', '5 mins', '1 hour', '1 day')
            **kwargs: Additional arguments for MarketDataService.get_historical_bars

        Returns:
            pandas DataFrame with OHLCV data

        Examples:
            >>> bars = await client.get_historical_bars("AAPL", "1 D", "1 min")
            >>> print(bars.head())
        """
        return await self.market_data.get_historical_bars(
            symbol=symbol,
            duration=duration,
            bar_size=bar_size,
            **kwargs
        )

    async def get_multiple_historical_bars(
        self,
        symbols: List[str],
        duration: str = "1 D",
        bar_size: str = "1 min",
        concurrent: bool = True,
        **kwargs
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch historical bars for multiple symbols.

        Args:
            symbols: List of ticker symbols
            duration: How far back to fetch
            bar_size: Bar size
            concurrent: Fetch concurrently (True) or sequentially (False)
            **kwargs: Additional arguments

        Returns:
            Dictionary mapping symbol to DataFrame

        Examples:
            >>> data = await client.get_multiple_historical_bars(
            ...     ['AAPL', 'GOOGL', 'MSFT'],
            ...     duration='1 D',
            ...     bar_size='5 mins'
            ... )
        """
        return await self.market_data.get_multiple_historical_bars(
            symbols=symbols,
            duration=duration,
            bar_size=bar_size,
            concurrent=concurrent,
            **kwargs
        )

    async def download_extended_history(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        bar_size: str = "1 day",
        **kwargs
    ) -> pd.DataFrame:
        """
        Download extended historical data using pagination.

        Args:
            symbol: Ticker symbol
            start_date: Start date
            end_date: End date
            bar_size: Bar size (recommend '1 day' for long ranges)
            **kwargs: Additional arguments

        Returns:
            pandas DataFrame with historical data

        Examples:
            >>> from datetime import datetime
            >>> start = datetime(2020, 1, 1)
            >>> end = datetime(2024, 1, 1)
            >>> data = await client.download_extended_history('AAPL', start, end)
        """
        return await self.market_data.download_extended_history(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            bar_size=bar_size,
            **kwargs
        )

    def get_remaining_requests(self) -> int:
        """
        Get remaining API requests available in rate limit window.

        Returns:
            Number of remaining requests

        Examples:
            >>> remaining = client.get_remaining_requests()
            >>> print(f"Remaining requests: {remaining}")
        """
        return self.market_data.get_remaining_requests()

    # Portfolio Methods

    async def get_positions(self) -> List[Position]:
        """
        Get current positions.

        Returns:
            List of Position objects

        Examples:
            >>> positions = await client.get_positions()
            >>> for pos in positions:
            ...     print(f"{pos.symbol}: {pos.position} @ ${pos.market_price}")
        """
        return await self.portfolio.get_positions()

    async def get_account_summary(
        self,
        account: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, float]:
        """
        Get account summary.

        Args:
            account: Account ID (optional)
            tags: List of specific tags to retrieve (optional)

        Returns:
            Dictionary of account metrics

        Examples:
            >>> summary = await client.get_account_summary()
            >>> print(f"Net Liquidation: ${summary['NetLiquidation']:,.2f}")
            >>> print(f"Buying Power: ${summary['BuyingPower']:,.2f}")
        """
        return await self.portfolio.get_account_summary(account, tags)

    async def get_account_values(
        self,
        account: Optional[str] = None
    ) -> Dict[str, float]:
        """
        Get detailed account values.

        Args:
            account: Account ID (optional)

        Returns:
            Dictionary of account values

        Examples:
            >>> values = await client.get_account_values()
            >>> for key, value in values.items():
            ...     print(f"{key}: {value}")
        """
        return await self.portfolio.get_account_values(account)

    def subscribe_portfolio_updates(
        self,
        callback: Callable[[PortfolioUpdate], None]
    ):
        """
        Subscribe to real-time portfolio updates.

        Args:
            callback: Function to call on portfolio update

        Examples:
            >>> def on_update(update: PortfolioUpdate):
            ...     pos = update.position
            ...     print(f"Update: {pos.symbol} - ${pos.unrealized_pnl:.2f}")
            >>> client.subscribe_portfolio_updates(on_update)
        """
        self.portfolio.subscribe_portfolio_updates(callback)

    def unsubscribe_portfolio_updates(self):
        """
        Unsubscribe from portfolio updates.

        Examples:
            >>> client.unsubscribe_portfolio_updates()
        """
        self.portfolio.unsubscribe_portfolio_updates()

    async def subscribe_pnl(
        self,
        account: str,
        callback: Callable[[PnLUpdate], None]
    ):
        """
        Subscribe to account-level PnL updates.

        Args:
            account: Account ID
            callback: Function to call on PnL update

        Examples:
            >>> def on_pnl(pnl: PnLUpdate):
            ...     print(f"Daily PnL: ${pnl.daily_pnl:.2f}")
            >>> await client.subscribe_pnl("DU123456", on_pnl)
        """
        await self.portfolio.subscribe_pnl(account, callback)

    async def subscribe_pnl_single(
        self,
        account: str,
        contract_id: int,
        callback: Callable[[PnLSingleUpdate], None]
    ):
        """
        Subscribe to position-level PnL updates.

        Args:
            account: Account ID
            contract_id: Contract ID
            callback: Function to call on PnL update

        Examples:
            >>> def on_pos_pnl(pnl: PnLSingleUpdate):
            ...     print(f"Position PnL: ${pnl.unrealized_pnl:.2f}")
            >>> await client.subscribe_pnl_single("DU123456", 12345, on_pos_pnl)
        """
        await self.portfolio.subscribe_pnl_single(account, contract_id, callback)

    async def unsubscribe_all_pnl(self):
        """
        Unsubscribe from all PnL updates.

        Examples:
            >>> await client.unsubscribe_all_pnl()
        """
        await self.portfolio.unsubscribe_all_pnl()

    # Context Manager Support

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        self.disconnect()
