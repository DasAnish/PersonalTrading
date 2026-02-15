"""
Tests for market data operations.
"""

import pytest
import pandas as pd
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock
from ib_insync import BarData, Contract
from ib_wrapper.market_data import MarketDataService
from ib_wrapper.exceptions import InvalidContractException


@pytest.mark.asyncio
async def test_get_historical_bars(mock_ib):
    """Test fetching historical bars."""
    service = MarketDataService(mock_ib)

    # Mock contract qualification
    mock_contract = Contract(symbol="AAPL", conId=12345)
    mock_ib.qualifyContractsAsync = AsyncMock(return_value=[mock_contract])

    # Mock historical data
    mock_bars = [
        BarData(
            date=datetime(2024, 1, 1, 9, 30),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000,
            average=100.25,
            barCount=10
        )
    ]
    mock_ib.reqHistoricalDataAsync = AsyncMock(return_value=mock_bars)

    # Test
    result = await service.get_historical_bars("AAPL", "1 D", "1 min")

    assert isinstance(result, pd.DataFrame)
    assert len(result) > 0
    mock_ib.qualifyContractsAsync.assert_called_once()
    mock_ib.reqHistoricalDataAsync.assert_called_once()


@pytest.mark.asyncio
async def test_get_historical_bars_invalid_contract(mock_ib):
    """Test handling of invalid contract."""
    service = MarketDataService(mock_ib)

    # Mock empty qualification result
    mock_ib.qualifyContractsAsync = AsyncMock(return_value=[])

    # Test
    with pytest.raises(InvalidContractException):
        await service.get_historical_bars("INVALID", "1 D", "1 min")


@pytest.mark.asyncio
async def test_get_multiple_historical_bars(mock_ib):
    """Test fetching multiple symbols."""
    service = MarketDataService(mock_ib)

    # Mock successful responses
    mock_contract = Contract(symbol="TEST", conId=12345)
    mock_ib.qualifyContractsAsync = AsyncMock(return_value=[mock_contract])
    mock_ib.reqHistoricalDataAsync = AsyncMock(return_value=[])

    symbols = ["AAPL", "GOOGL"]
    result = await service.get_multiple_historical_bars(
        symbols,
        "1 D",
        "1 min",
        concurrent=False
    )

    assert isinstance(result, dict)
    assert len(result) <= len(symbols)


def test_get_remaining_requests(mock_ib):
    """Test getting remaining rate limit requests."""
    service = MarketDataService(mock_ib, rate_limit_requests=50)

    remaining = service.get_remaining_requests()

    assert isinstance(remaining, int)
    assert 0 <= remaining <= 50
