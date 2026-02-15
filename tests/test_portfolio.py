"""
Tests for portfolio operations.
"""

import pytest
from unittest.mock import MagicMock
from ib_insync import Position as IBPosition, Contract
from ib_wrapper.portfolio import PortfolioService
from ib_wrapper.models import Position


@pytest.mark.asyncio
async def test_get_positions(mock_ib):
    """Test getting positions."""
    service = PortfolioService(mock_ib)

    # Mock positions
    contract = Contract(symbol="AAPL", conId=12345)
    mock_positions = [
        MagicMock(
            contract=contract,
            position=100,
            marketPrice=150.0,
            marketValue=15000.0,
            averageCost=145.0,
            unrealizedPNL=500.0,
            realizedPNL=0.0,
            account="DU123456"
        )
    ]
    mock_ib.positions.return_value = mock_positions

    # Test
    positions = await service.get_positions()

    assert isinstance(positions, list)
    assert len(positions) == 1
    assert isinstance(positions[0], Position)
    assert positions[0].symbol == "AAPL"
    assert positions[0].position == 100


@pytest.mark.asyncio
async def test_get_account_summary(mock_ib):
    """Test getting account summary."""
    service = PortfolioService(mock_ib)

    # Mock account summary
    mock_summary = [
        MagicMock(tag="NetLiquidation", value="100000.00"),
        MagicMock(tag="BuyingPower", value="200000.00"),
    ]
    mock_ib.accountSummary.return_value = mock_summary

    # Test
    summary = await service.get_account_summary()

    assert isinstance(summary, dict)
    assert "NetLiquidation" in summary
    assert summary["NetLiquidation"] == 100000.0


@pytest.mark.asyncio
async def test_get_account_values(mock_ib):
    """Test getting account values."""
    service = PortfolioService(mock_ib)

    # Mock account values
    mock_values = [
        MagicMock(tag="CashBalance", currency="USD", value="50000.00"),
    ]
    mock_ib.accountValues.return_value = mock_values

    # Test
    values = await service.get_account_values()

    assert isinstance(values, dict)
    assert len(values) > 0


def test_subscribe_portfolio_updates(mock_ib):
    """Test subscribing to portfolio updates."""
    service = PortfolioService(mock_ib)
    mock_ib.updatePortfolioEvent = MagicMock()

    callback = MagicMock()
    service.subscribe_portfolio_updates(callback)

    assert service._portfolio_callback is not None


def test_unsubscribe_portfolio_updates(mock_ib):
    """Test unsubscribing from portfolio updates."""
    service = PortfolioService(mock_ib)
    mock_ib.updatePortfolioEvent = MagicMock()

    callback = MagicMock()
    service.subscribe_portfolio_updates(callback)
    service.unsubscribe_portfolio_updates()

    assert service._portfolio_callback is None
