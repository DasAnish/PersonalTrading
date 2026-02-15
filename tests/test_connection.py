"""
Tests for connection management.
"""

import pytest
from unittest.mock import MagicMock
from ib_wrapper.connection import IBConnectionManager
from ib_wrapper.exceptions import ConnectionException


@pytest.mark.asyncio
async def test_connect_success(connection_config, mock_ib):
    """Test successful connection."""
    manager = IBConnectionManager(connection_config)
    manager.ib = mock_ib

    result = await manager.connect()

    assert result is True
    assert manager.is_connected() is True
    mock_ib.connect.assert_called_once()


@pytest.mark.asyncio
async def test_connect_failure(connection_config, mock_ib):
    """Test connection failure handling."""
    manager = IBConnectionManager(connection_config, max_retries=2)
    manager.ib = mock_ib
    mock_ib.connect.side_effect = Exception("Connection failed")
    mock_ib.isConnected.return_value = False

    with pytest.raises(ConnectionException):
        await manager.connect()


@pytest.mark.asyncio
async def test_disconnect(connection_config, mock_ib):
    """Test disconnection."""
    manager = IBConnectionManager(connection_config)
    manager.ib = mock_ib
    manager._connected = True

    manager.disconnect()

    mock_ib.disconnect.assert_called_once()
    assert manager._connected is False


@pytest.mark.asyncio
async def test_is_connected(connection_config, mock_ib):
    """Test connection status check."""
    manager = IBConnectionManager(connection_config)
    manager.ib = mock_ib
    manager._connected = True

    assert manager.is_connected() is True

    manager._connected = False
    assert manager.is_connected() is False


@pytest.mark.asyncio
async def test_context_manager(connection_config, mock_ib):
    """Test async context manager."""
    manager = IBConnectionManager(connection_config)
    manager.ib = mock_ib

    async with manager as conn:
        assert conn is manager
        mock_ib.connect.assert_called_once()

    mock_ib.disconnect.assert_called_once()
