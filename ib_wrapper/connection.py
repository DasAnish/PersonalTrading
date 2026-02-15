"""
Connection management for Interactive Brokers wrapper.

This module handles the lifecycle of IB connections, including
connection establishment, health monitoring, automatic reconnection,
and graceful shutdown.
"""

import asyncio
import logging
from typing import Optional, Callable

from ib_insync import IB

from .exceptions import ConnectionException
from .models import ConnectionConfig

logger = logging.getLogger(__name__)


class IBConnectionManager:
    """
    Manages the lifecycle of IB connection with automatic reconnection.

    This class handles:
    - Connection establishment with retry logic
    - Connection health monitoring
    - Automatic reconnection on disconnect
    - Event handlers for connection state changes
    - Graceful shutdown
    """

    def __init__(
        self,
        config: ConnectionConfig,
        max_retries: int = 3,
        backoff: float = 2.0
    ):
        """
        Initialize connection manager.

        Args:
            config: Connection configuration
            max_retries: Maximum number of connection retry attempts
            backoff: Initial backoff time in seconds (doubles each retry)
        """
        self.config = config
        self.max_retries = max_retries
        self.backoff = backoff

        self.ib = IB()
        self._connected = False
        self._error_callback: Optional[Callable] = None
        self._disconnect_callback: Optional[Callable] = None
        self._connect_callback: Optional[Callable] = None

    async def connect(self) -> bool:
        """
        Establish connection to IB Gateway/TWS with retry logic.

        Returns:
            True if connection successful, False otherwise

        Raises:
            ConnectionException: If all connection attempts fail
        """
        for attempt in range(self.max_retries):
            try:
                logger.info(
                    f"Attempting to connect to IB at {self.config.host}:{self.config.port} "
                    f"(attempt {attempt + 1}/{self.max_retries})"
                )

                await self.ib.connectAsync(
                    host=self.config.host,
                    port=self.config.port,
                    clientId=self.config.client_id,
                    timeout=self.config.timeout,
                    readonly=self.config.readonly
                )

                # Wait a moment for connection to stabilize
                await asyncio.sleep(0.5)

                if self.ib.isConnected():
                    self._connected = True
                    self._setup_event_handlers()
                    logger.info("Successfully connected to IB")

                    if self._connect_callback:
                        self._connect_callback()

                    return True
                else:
                    raise ConnectionException("Connection established but not active")

            except Exception as e:
                logger.error(f"Connection attempt {attempt + 1} failed: {e}")

                if attempt < self.max_retries - 1:
                    wait_time = self.backoff * (2 ** attempt)
                    logger.info(f"Retrying in {wait_time:.2f} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    raise ConnectionException(
                        f"Failed to connect after {self.max_retries} attempts: {e}"
                    )

        return False

    def disconnect(self):
        """
        Gracefully disconnect from IB.
        """
        if self.ib.isConnected():
            logger.info("Disconnecting from IB...")
            self.ib.disconnect()
            self._connected = False
            logger.info("Disconnected from IB")

    def is_connected(self) -> bool:
        """
        Check if connection is active.

        Returns:
            True if connected, False otherwise
        """
        return self.ib.isConnected() and self._connected

    async def reconnect(self) -> bool:
        """
        Reconnect to IB after connection loss.

        Returns:
            True if reconnection successful, False otherwise
        """
        logger.info("Attempting to reconnect to IB...")
        self.disconnect()
        await asyncio.sleep(1)
        return await self.connect()

    async def wait_for_connection(self, timeout: Optional[float] = None):
        """
        Wait for connection to be established.

        Args:
            timeout: Maximum time to wait in seconds (optional)

        Raises:
            ConnectionException: If timeout expires
        """
        start_time = asyncio.get_event_loop().time()

        while not self.is_connected():
            if timeout and (asyncio.get_event_loop().time() - start_time) > timeout:
                raise ConnectionException(f"Connection timeout after {timeout} seconds")

            await asyncio.sleep(0.1)

    def _setup_event_handlers(self):
        """
        Setup event handlers for IB connection events.
        """
        # Error event handler
        def on_error(reqId, errorCode, errorString, contract):
            """Handle IB error events."""
            # Informational messages (2000-2999)
            if 2000 <= errorCode < 3000:
                logger.info(f"IB Info ({errorCode}): {errorString}")
                return

            # Warning messages (300-399, 400-499)
            if (300 <= errorCode < 400) or (400 <= errorCode < 500):
                logger.warning(f"IB Warning ({errorCode}): {errorString}")
                return

            # System messages (1000-1999)
            if 1000 <= errorCode < 2000:
                if errorCode == 1100:  # Connectivity lost
                    logger.error("Connection lost - attempting reconnect")
                    self._connected = False
                    asyncio.create_task(self.reconnect())
                elif errorCode == 1101:  # Connectivity restored (data lost)
                    logger.warning("Connection restored but data lost")
                elif errorCode == 1102:  # Connectivity restored
                    logger.info("Connection restored")
                    self._connected = True
                else:
                    logger.error(f"IB System ({errorCode}): {errorString}")
                return

            # Error messages
            logger.error(f"IB Error ({errorCode}): {errorString}")

            # Call custom error callback
            if self._error_callback:
                self._error_callback(errorCode, errorString)

        # Disconnection event handler
        def on_disconnect():
            """Handle disconnection event."""
            logger.warning("Disconnected from IB")
            self._connected = False

            if self._disconnect_callback:
                self._disconnect_callback()

        # Register handlers
        self.ib.errorEvent += on_error
        self.ib.disconnectedEvent += on_disconnect

        logger.debug("Event handlers registered")

    def on_error(self, callback: Callable):
        """
        Register callback for error events.

        Args:
            callback: Function to call on error (errorCode, errorString)
        """
        self._error_callback = callback

    def on_disconnect(self, callback: Callable):
        """
        Register callback for disconnection events.

        Args:
            callback: Function to call on disconnect
        """
        self._disconnect_callback = callback

    def on_connect(self, callback: Callable):
        """
        Register callback for connection events.

        Args:
            callback: Function to call on successful connection
        """
        self._connect_callback = callback

    async def __aenter__(self):
        """
        Async context manager entry.

        Returns:
            Self instance
        """
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Async context manager exit.
        """
        self.disconnect()

    def __del__(self):
        """
        Cleanup on deletion.
        """
        if hasattr(self, 'ib') and self.ib.isConnected():
            self.disconnect()
