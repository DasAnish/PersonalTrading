"""
Pytest configuration and fixtures for testing IB wrapper.
"""

import pytest
import asyncio
from unittest.mock import Mock, MagicMock
from ib_insync import IB
from ib_wrapper import IBClient, Config
from ib_wrapper.connection import IBConnectionManager
from ib_wrapper.models import ConnectionConfig


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_ib():
    """Mock IB instance for testing."""
    mock = MagicMock(spec=IB)
    mock.isConnected.return_value = True
    mock.connect.return_value = None
    mock.disconnect.return_value = None
    mock.positions.return_value = []
    mock.accountSummary.return_value = []
    mock.accountValues.return_value = []
    return mock


@pytest.fixture
def test_config():
    """Test configuration."""
    config = Config()
    # Override with test values
    config._config['ib_connection'] = {
        'host': '127.0.0.1',
        'port': 7497,
        'client_id': 999,
        'timeout': 5,
        'readonly': True
    }
    return config


@pytest.fixture
def connection_config():
    """Connection configuration for testing."""
    return ConnectionConfig(
        host='127.0.0.1',
        port=7497,
        client_id=999,
        timeout=5,
        readonly=True
    )


@pytest.fixture
async def client(test_config, mock_ib):
    """Create test client with mocked IB instance."""
    client = IBClient(test_config)
    client.connection.ib = mock_ib
    yield client
    # Cleanup
    if client.is_connected():
        client.disconnect()
