"""
Utility functions and helpers for Interactive Brokers wrapper.

This module provides helper functions for contract creation, validation,
rate limiting, and retry logic.
"""

import asyncio
import time
import logging
from collections import deque
from functools import wraps
from typing import Callable, Any, Optional
from datetime import timedelta

from ib_insync import Contract

from .exceptions import RateLimitException

logger = logging.getLogger(__name__)


def create_contract(
    symbol: str,
    sec_type: str = 'STK',
    exchange: str = 'SMART',
    currency: str = 'USD',
    **kwargs
) -> Contract:
    """
    Create an IB contract from simple parameters.

    Args:
        symbol: Ticker symbol (e.g., 'AAPL', 'GOOGL')
        sec_type: Security type ('STK' for stock, 'OPT' for option, etc.)
        exchange: Exchange code (default 'SMART' for smart routing)
        currency: Currency code (default 'USD')
        **kwargs: Additional contract parameters

    Returns:
        ib_insync Contract object

    Examples:
        >>> create_contract('AAPL')
        >>> create_contract('EUR', sec_type='CASH', exchange='IDEALPRO', currency='USD')
    """
    contract = Contract()
    contract.symbol = symbol
    contract.secType = sec_type
    contract.exchange = exchange
    contract.currency = currency

    # Apply any additional parameters
    for key, value in kwargs.items():
        setattr(contract, key, value)

    return contract


def parse_duration(duration_str: str) -> timedelta:
    """
    Parse IB duration string to timedelta.

    Args:
        duration_str: IB duration string (e.g., '1 D', '2 W', '6 M', '1 Y')

    Returns:
        timedelta object

    Examples:
        >>> parse_duration('1 D')
        timedelta(days=1)
        >>> parse_duration('2 W')
        timedelta(days=14)
    """
    parts = duration_str.strip().split()
    if len(parts) != 2:
        raise ValueError(f"Invalid duration string: {duration_str}")

    value = int(parts[0])
    unit = parts[1].upper()

    if unit == 'S':
        return timedelta(seconds=value)
    elif unit == 'D':
        return timedelta(days=value)
    elif unit == 'W':
        return timedelta(weeks=value)
    elif unit == 'M':
        return timedelta(days=value * 30)  # Approximate
    elif unit == 'Y':
        return timedelta(days=value * 365)  # Approximate
    else:
        raise ValueError(f"Unknown duration unit: {unit}")


def validate_bar_size(bar_size: str) -> bool:
    """
    Validate bar size string against IB API valid values.

    Args:
        bar_size: Bar size string (e.g., '1 min', '5 mins', '1 hour', '1 day')

    Returns:
        True if valid, False otherwise

    Valid bar sizes:
        '1 secs', '5 secs', '10 secs', '15 secs', '30 secs',
        '1 min', '2 mins', '3 mins', '5 mins', '10 mins', '15 mins', '20 mins', '30 mins',
        '1 hour', '2 hours', '3 hours', '4 hours', '8 hours',
        '1 day', '1 week', '1 month'
    """
    valid_bar_sizes = {
        '1 secs', '5 secs', '10 secs', '15 secs', '30 secs',
        '1 min', '2 mins', '3 mins', '5 mins', '10 mins', '15 mins', '20 mins', '30 mins',
        '1 hour', '2 hours', '3 hours', '4 hours', '8 hours',
        '1 day', '1 week', '1 month'
    }
    return bar_size in valid_bar_sizes


class RateLimiter:
    """
    Rate limiter for IB API requests using sliding window algorithm.

    IB has strict rate limits (e.g., 50 requests per 10 minutes for historical data).
    This class enforces rate limits to prevent pacing violations.
    """

    def __init__(self, max_requests: int = 50, window: int = 600):
        """
        Initialize rate limiter.

        Args:
            max_requests: Maximum number of requests allowed in the window
            window: Time window in seconds (default 600 = 10 minutes)
        """
        self.max_requests = max_requests
        self.window = window
        self.requests = deque()
        self._lock = asyncio.Lock()

    async def acquire(self):
        """
        Acquire permission to make a request.

        This method will block if the rate limit is exceeded until a slot becomes available.

        Raises:
            RateLimitException: If waiting for rate limit would take too long
        """
        async with self._lock:
            now = time.time()

            # Remove requests outside the window
            while self.requests and self.requests[0] < now - self.window:
                self.requests.popleft()

            # Check if we're at the limit
            if len(self.requests) >= self.max_requests:
                # Calculate wait time
                wait_time = self.requests[0] + self.window - now

                if wait_time > 0:
                    logger.warning(
                        f"Rate limit reached. Waiting {wait_time:.2f} seconds..."
                    )
                    await asyncio.sleep(wait_time)

                    # Clean up old requests after waiting
                    now = time.time()
                    while self.requests and self.requests[0] < now - self.window:
                        self.requests.popleft()

            # Record this request
            self.requests.append(now)

    def get_remaining_requests(self) -> int:
        """
        Get the number of remaining requests available.

        Returns:
            Number of remaining requests in current window
        """
        now = time.time()
        # Remove old requests
        while self.requests and self.requests[0] < now - self.window:
            self.requests.popleft()

        return max(0, self.max_requests - len(self.requests))


def rate_limited(rate_limiter: RateLimiter):
    """
    Decorator to apply rate limiting to async functions.

    Args:
        rate_limiter: RateLimiter instance to use

    Example:
        >>> limiter = RateLimiter(max_requests=50, window=600)
        >>> @rate_limited(limiter)
        >>> async def fetch_data():
        >>>     pass
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            await rate_limiter.acquire()
            return await func(*args, **kwargs)

        return wrapper

    return decorator


async def retry_on_failure(
    func: Callable,
    max_retries: int = 3,
    backoff: float = 1.0,
    exceptions: tuple = (Exception,)
) -> Any:
    """
    Retry an async function with exponential backoff on failure.

    Args:
        func: Async function to retry
        max_retries: Maximum number of retry attempts
        backoff: Initial backoff time in seconds (doubles each retry)
        exceptions: Tuple of exceptions to catch and retry on

    Returns:
        Result of the function call

    Raises:
        The last exception if all retries fail

    Example:
        >>> result = await retry_on_failure(
        >>>     lambda: fetch_data(),
        >>>     max_retries=3,
        >>>     backoff=1.0
        >>> )
    """
    last_exception = None

    for attempt in range(max_retries):
        try:
            return await func()
        except exceptions as e:
            last_exception = e
            if attempt < max_retries - 1:
                wait_time = backoff * (2 ** attempt)
                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries} failed: {e}. "
                    f"Retrying in {wait_time:.2f} seconds..."
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error(
                    f"All {max_retries} attempts failed. Last error: {e}"
                )

    raise last_exception


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    console: bool = True
) -> logging.Logger:
    """
    Setup logging configuration for the IB wrapper.

    Args:
        level: Logging level ('DEBUG', 'INFO', 'WARNING', 'ERROR')
        log_file: Path to log file (optional)
        console: Whether to log to console (default True)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("ib_wrapper")
    logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    logger.handlers.clear()

    # Console handler
    if console:
        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter(
            '%(levelname)s - %(name)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    # File handler
    if log_file:
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5
        )
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger
