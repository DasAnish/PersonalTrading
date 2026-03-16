"""
Market data service for Interactive Brokers wrapper.

This module handles historical market data operations with rate limiting,
batch fetching, and extended history downloads.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import pandas as pd
from ib_insync import IB, util

from .utils import create_contract, RateLimiter, retry_on_failure
from .exceptions import DataRequestException, InvalidContractException, RateLimitException

logger = logging.getLogger(__name__)


class MarketDataService:
    """
    Service for fetching historical market data from IB.

    Handles:
    - Single symbol historical bars
    - Batch fetching for multiple symbols
    - Extended history downloads (pagination)
    - Rate limiting (50 requests per 10 minutes)
    - Error handling and retries
    """

    def __init__(
        self,
        ib: IB,
        rate_limit_requests: int = 50,
        rate_limit_window: int = 600
    ):
        """
        Initialize market data service.

        Args:
            ib: ib_insync IB instance
            rate_limit_requests: Max requests per window (default 50)
            rate_limit_window: Time window in seconds (default 600 = 10 min)
        """
        self.ib = ib
        self.rate_limiter = RateLimiter(
            max_requests=rate_limit_requests,
            window=rate_limit_window
        )

    async def get_historical_bars(
        self,
        symbol: str,
        duration: str = "1 D",
        bar_size: str = "1 min",
        what_to_show: str = "TRADES",
        use_rth: bool = True,
        end_datetime: Optional[datetime] = None,
        sec_type: str = 'STK',
        exchange: str = 'SMART',
        currency: str = 'USD'
    ) -> pd.DataFrame:
        """
        Fetch historical bars for a single symbol.

        Args:
            symbol: Ticker symbol (e.g., 'AAPL')
            duration: How far back to fetch (e.g., '1 D', '1 W', '1 M', '1 Y')
            bar_size: Bar size (e.g., '1 min', '5 mins', '1 hour', '1 day')
            what_to_show: Data type ('TRADES', 'MIDPOINT', 'BID', 'ASK')
            use_rth: Use regular trading hours only (default True)
            end_datetime: End date/time (default now)
            sec_type: Security type (default 'STK' for stocks)
            exchange: Exchange (default 'SMART')
            currency: Currency (default 'USD')

        Returns:
            pandas DataFrame with OHLCV data

        Raises:
            InvalidContractException: If contract is invalid
            DataRequestException: If data request fails
        """
        try:
            # Create contract
            contract = create_contract(
                symbol=symbol,
                sec_type=sec_type,
                exchange=exchange,
                currency=currency
            )

            # Qualify contract
            logger.debug(f"Qualifying contract for {symbol}")
            qualified = await self.ib.qualifyContractsAsync(contract)

            if not qualified:
                raise InvalidContractException(
                    f"Invalid contract: {symbol} ({sec_type})"
                )

            # Apply rate limiting
            await self.rate_limiter.acquire()

            # Request historical data
            logger.info(
                f"Fetching {duration} of {bar_size} bars for {symbol}"
            )

            try:
                bars = await self.ib.reqHistoricalDataAsync(
                    qualified[0],
                    endDateTime=end_datetime or '',
                    durationStr=duration,
                    barSizeSetting=bar_size,
                    whatToShow=what_to_show,
                    useRTH=use_rth
                )
            except Exception as e:
                if "cannot insert" in str(e) or "already exists" in str(e):
                    logger.warning(
                        f"ib_insync duplicate-date error for {symbol} ({e}); "
                        "skipping live fetch, will use cache"
                    )
                    return pd.DataFrame()
                raise

            if not bars:
                logger.warning(f"No data returned for {symbol}")
                return pd.DataFrame()

            # Convert to DataFrame — ib_insync raises "cannot insert date, already
            # exists" for some LSE ETFs that return duplicate timestamps.  Fall
            # back to manual construction in that case.
            try:
                df = util.df(bars)
            except Exception as e:
                logger.warning(f"util.df failed for {symbol} ({e}), building DataFrame manually")
                records = [
                    {
                        "open": b.open, "high": b.high, "low": b.low,
                        "close": b.close, "volume": b.volume,
                        "average": getattr(b, "average", None),
                        "barCount": getattr(b, "barCount", None),
                    }
                    for b in bars
                ]
                dates = pd.to_datetime([b.date for b in bars])
                df = pd.DataFrame(records, index=dates)
                df.index.name = "date"
                # Drop duplicates that triggered the original error
                df = df[~df.index.duplicated(keep="first")]

            # Force set datetime index from bars to ensure it's proper DatetimeIndex
            if not df.empty and bars:
                try:
                    if not isinstance(df.index, pd.DatetimeIndex):
                        dates = pd.to_datetime([bar.date for bar in bars])
                        df.index = dates
                        df.index.name = 'date'
                        df = df[~df.index.duplicated(keep='first')]
                except Exception as e:
                    logger.warning(f"Could not set datetime index: {e}")

            logger.info(f"Received {len(df)} bars for {symbol}")
            return df

        except InvalidContractException:
            raise
        except Exception as e:
            logger.error(f"Failed to fetch historical data for {symbol}: {e}")
            raise DataRequestException(f"Failed to fetch data for {symbol}: {e}")

    async def get_multiple_historical_bars(
        self,
        symbols: List[str],
        duration: str = "1 D",
        bar_size: str = "1 min",
        what_to_show: str = "TRADES",
        use_rth: bool = True,
        concurrent: bool = True,
        **kwargs
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch historical bars for multiple symbols.

        Args:
            symbols: List of ticker symbols
            duration: How far back to fetch
            bar_size: Bar size
            what_to_show: Data type
            use_rth: Use regular trading hours only
            concurrent: Fetch concurrently (True) or sequentially (False)
            **kwargs: Additional arguments to pass to get_historical_bars

        Returns:
            Dictionary mapping symbol to DataFrame

        Examples:
            >>> data = await service.get_multiple_historical_bars(
            ...     ['AAPL', 'GOOGL', 'MSFT'],
            ...     duration='1 D',
            ...     bar_size='5 mins'
            ... )
        """
        results = {}

        if concurrent:
            # Concurrent fetching (faster but uses rate limit quota)
            logger.info(f"Fetching data for {len(symbols)} symbols concurrently")

            tasks = []
            for symbol in symbols:
                task = self.get_historical_bars(
                    symbol=symbol,
                    duration=duration,
                    bar_size=bar_size,
                    what_to_show=what_to_show,
                    use_rth=use_rth,
                    **kwargs
                )
                tasks.append((symbol, task))

            # Gather results
            task_results = await asyncio.gather(
                *[task for _, task in tasks],
                return_exceptions=True
            )

            # Process results
            for (symbol, _), result in zip(tasks, task_results):
                if isinstance(result, Exception):
                    logger.error(f"Failed to fetch {symbol}: {result}")
                else:
                    results[symbol] = result

        else:
            # Sequential fetching (slower but more reliable)
            logger.info(f"Fetching data for {len(symbols)} symbols sequentially")

            for symbol in symbols:
                try:
                    df = await self.get_historical_bars(
                        symbol=symbol,
                        duration=duration,
                        bar_size=bar_size,
                        what_to_show=what_to_show,
                        use_rth=use_rth,
                        **kwargs
                    )
                    results[symbol] = df

                except Exception as e:
                    logger.error(f"Failed to fetch {symbol}: {e}")

        logger.info(
            f"Successfully fetched data for {len(results)}/{len(symbols)} symbols"
        )
        return results

    async def download_extended_history(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        bar_size: str = "1 day",
        what_to_show: str = "TRADES",
        use_rth: bool = True,
        **kwargs
    ) -> pd.DataFrame:
        """
        Download historical data beyond single request limits using pagination.

        IB limits the amount of data per request. This method fetches data
        in chunks and combines them.

        Args:
            symbol: Ticker symbol
            start_date: Start date for data
            end_date: End date for data
            bar_size: Bar size (recommend '1 day' for long ranges)
            what_to_show: Data type
            use_rth: Use regular trading hours only
            **kwargs: Additional arguments

        Returns:
            pandas DataFrame with combined historical data

        Examples:
            >>> start = datetime(2020, 1, 1)
            >>> end = datetime(2024, 1, 1)
            >>> data = await service.download_extended_history(
            ...     'AAPL', start, end, bar_size='1 day'
            ... )
        """
        logger.info(
            f"Downloading extended history for {symbol} "
            f"from {start_date} to {end_date}"
        )

        all_bars = []
        current_end = end_date

        # Determine duration per chunk based on bar size
        duration = "1 Y"  # Default to 1 year chunks

        chunk_count = 0
        while current_end > start_date:
            try:
                logger.debug(
                    f"Fetching chunk {chunk_count + 1} ending at {current_end}"
                )

                # Fetch chunk
                df = await self.get_historical_bars(
                    symbol=symbol,
                    duration=duration,
                    bar_size=bar_size,
                    what_to_show=what_to_show,
                    use_rth=use_rth,
                    end_datetime=current_end,
                    **kwargs
                )

                if df.empty:
                    logger.warning(f"No more data available before {current_end}")
                    break

                all_bars.append(df)
                chunk_count += 1

                # Move end date back for next chunk
                # Get the first date from the dataframe
                if hasattr(df.index, 'to_pydatetime'):
                    first_date = df.index[0].to_pydatetime()
                else:
                    first_date = df.index[0]

                # Ensure first_date is a datetime object
                if isinstance(first_date, datetime):
                    current_end = first_date - timedelta(days=1)
                else:
                    logger.warning(f"Could not extract datetime from index: {type(first_date)}")
                    break

                # Stop if we've gone before start_date
                if current_end < start_date:
                    break

                # Small delay between chunks to be nice to IB
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Error fetching chunk: {e}")
                break

        if not all_bars:
            logger.warning(f"No data fetched for {symbol}")
            return pd.DataFrame()

        # Combine all chunks
        combined = pd.concat(all_bars, axis=0)

        # Remove duplicates and sort
        combined = combined[~combined.index.duplicated(keep='first')]
        combined = combined.sort_index()

        # Filter to requested date range
        combined = combined[
            (combined.index >= start_date) &
            (combined.index <= end_date)
        ]

        logger.info(
            f"Downloaded {len(combined)} bars for {symbol} "
            f"({chunk_count} chunks)"
        )

        return combined

    def get_remaining_requests(self) -> int:
        """
        Get the number of remaining requests available.

        Returns:
            Number of remaining requests in current rate limit window
        """
        return self.rate_limiter.get_remaining_requests()
