"""
Unit tests for Phase 1: Core Architecture (new Strategy interface).

Tests the newly created:
- Strategy interface and base classes
- AssetStrategy implementation
- StrategyContext and DataRequirements
- MarketDataService singleton pattern
"""

import pytest
import pandas as pd
from datetime import datetime, timedelta
import numpy as np

from strategies.core import (
    Strategy, AssetStrategy, AllocationStrategy, OverlayStrategy,
    StrategyContext, DataRequirements
)
from data import MarketDataService, get_market_data


# ============================================================================
# Test Data Setup
# ============================================================================


@pytest.fixture
def sample_prices():
    """Create sample price data for testing."""
    dates = pd.date_range(start='2023-01-01', end='2023-12-31', freq='D')
    data = {
        'VUSA': np.random.randn(len(dates)).cumsum() + 100,
        'SSLN': np.random.randn(len(dates)).cumsum() + 50,
        'SGLN': np.random.randn(len(dates)).cumsum() + 40,
        'IWRD': np.random.randn(len(dates)).cumsum() + 80,
    }
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def vusa_asset():
    """Create VUSA asset strategy."""
    return AssetStrategy('VUSA', currency='GBP')


@pytest.fixture
def ssln_asset():
    """Create SSLN asset strategy."""
    return AssetStrategy('SSLN', currency='GBP')


# ============================================================================
# Test AssetStrategy
# ============================================================================


class TestAssetStrategy:
    """Test AssetStrategy implementation."""

    def test_asset_strategy_creation(self, vusa_asset):
        """Test AssetStrategy can be created with proper attributes."""
        assert vusa_asset.symbol == 'VUSA'
        assert vusa_asset.currency == 'GBP'
        assert vusa_asset.exchange == 'SMART'
        assert vusa_asset.name == 'VUSA'

    def test_asset_strategy_custom_name(self):
        """Test AssetStrategy with custom name."""
        asset = AssetStrategy('VUSA', currency='GBP', name='UK-Equities-ETF')
        assert asset.name == 'UK-Equities-ETF'
        assert asset.symbol == 'VUSA'

    def test_asset_calculate_weights(self, vusa_asset, sample_prices):
        """Test AssetStrategy always returns 100% to itself."""
        context = StrategyContext(
            current_date=datetime(2023, 6, 15),
            lookback_start=datetime(2023, 6, 1),
            prices=sample_prices.loc['2023-06-01':'2023-06-15']
        )

        weights = vusa_asset.calculate_weights(context)

        assert len(weights) == 1
        assert weights.index[0] == 'VUSA'
        assert weights.iloc[0] == 1.0

    def test_asset_get_price_timeseries(self, vusa_asset, sample_prices):
        """Test AssetStrategy returns correct price timeseries."""
        context = StrategyContext(
            current_date=datetime(2023, 6, 15),
            lookback_start=datetime(2023, 6, 1),
            prices=sample_prices.loc['2023-06-01':'2023-06-15']
        )

        prices = vusa_asset.get_price_timeseries(context)

        assert isinstance(prices, pd.Series)
        assert len(prices) == len(context.prices)
        pd.testing.assert_series_equal(prices, sample_prices['VUSA'].loc['2023-06-01':'2023-06-15'])

    def test_asset_get_data_requirements(self, vusa_asset):
        """Test AssetStrategy specifies correct data requirements."""
        req = vusa_asset.get_data_requirements()

        assert isinstance(req, DataRequirements)
        assert req.symbols == ['VUSA']
        assert req.lookback_days == 1  # Assets need minimal history
        assert req.currency == 'GBP'
        assert req.exchange == 'SMART'

    def test_asset_get_symbols(self, vusa_asset):
        """Test AssetStrategy returns correct symbols."""
        symbols = vusa_asset.get_symbols()
        assert symbols == ['VUSA']


# ============================================================================
# Test StrategyContext
# ============================================================================


class TestStrategyContext:
    """Test StrategyContext data class."""

    def test_context_creation(self, sample_prices):
        """Test StrategyContext can be created with all fields."""
        sliced_prices = sample_prices.loc['2023-06-01':'2023-06-15']

        context = StrategyContext(
            current_date=datetime(2023, 6, 15),
            lookback_start=datetime(2023, 6, 1),
            prices=sliced_prices,
            portfolio_values=None,
            metadata={'test_key': 'test_value'}
        )

        assert context.current_date == datetime(2023, 6, 15)
        assert context.lookback_start == datetime(2023, 6, 1)
        pd.testing.assert_frame_equal(context.prices, sliced_prices)
        assert context.portfolio_values is None
        assert context.metadata['test_key'] == 'test_value'

    def test_context_default_metadata(self, sample_prices):
        """Test StrategyContext has default empty metadata."""
        context = StrategyContext(
            current_date=datetime(2023, 6, 15),
            lookback_start=datetime(2023, 6, 1),
            prices=sample_prices.loc['2023-06-01':'2023-06-15']
        )

        assert context.metadata == {}


# ============================================================================
# Test DataRequirements
# ============================================================================


class TestDataRequirements:
    """Test DataRequirements data class."""

    def test_requirements_creation(self):
        """Test DataRequirements can be created."""
        req = DataRequirements(
            symbols=['VUSA', 'SSLN'],
            lookback_days=252,
            currency='GBP',
            exchange='SMART'
        )

        assert req.symbols == ['VUSA', 'SSLN']
        assert req.lookback_days == 252
        assert req.currency == 'GBP'
        assert req.frequency == '1 day'  # Default

    def test_requirements_defaults(self):
        """Test DataRequirements with defaults."""
        req = DataRequirements(
            symbols=['VUSA'],
            lookback_days=100
        )

        assert req.currency == 'USD'  # Default
        assert req.exchange == 'SMART'  # Default
        assert req.sec_type == 'STK'  # Default
        assert req.frequency == '1 day'  # Default

    def test_requirements_aggregate(self):
        """Test aggregating DataRequirements from multiple strategies."""
        req1 = DataRequirements(
            symbols=['VUSA', 'SSLN'],
            lookback_days=252,
            currency='GBP'
        )

        req2 = DataRequirements(
            symbols=['SGLN', 'IWRD'],
            lookback_days=504,  # More lookback needed
            currency='GBP'
        )

        aggregated = req1.aggregate_with(req2)

        assert set(aggregated.symbols) == {'VUSA', 'SSLN', 'SGLN', 'IWRD'}
        assert aggregated.lookback_days == 504  # Max of both
        assert aggregated.currency == 'GBP'


# ============================================================================
# Test MarketDataService Singleton
# ============================================================================


class TestMarketDataServiceSingleton:
    """Test MarketDataService singleton pattern."""

    def test_singleton_instance(self):
        """Test MarketDataService returns same instance."""
        mds1 = MarketDataService()
        mds2 = MarketDataService()

        assert mds1 is mds2

    def test_get_market_data_accessor(self):
        """Test get_market_data() convenience accessor."""
        mds1 = get_market_data()
        mds2 = get_market_data()

        assert mds1 is mds2
        assert isinstance(mds1, MarketDataService)

    def test_singleton_reset(self):
        """Test MarketDataService.reset() for testing."""
        mds1 = MarketDataService()
        MarketDataService.reset()
        mds2 = MarketDataService()

        assert mds1 is not mds2  # Different instances after reset


# ============================================================================
# Test Strategy Repr
# ============================================================================


class TestStrategyRepr:
    """Test Strategy __repr__ method."""

    def test_asset_repr_default_name(self):
        """Test AssetStrategy repr with default name."""
        asset = AssetStrategy('VUSA', currency='GBP')
        assert repr(asset) == "AssetStrategy(name='VUSA')"

    def test_asset_repr_custom_name(self):
        """Test AssetStrategy repr with custom name."""
        asset = AssetStrategy('VUSA', currency='GBP', name='MyAsset')
        assert repr(asset) == "AssetStrategy(name='MyAsset')"


# ============================================================================
# Test AssetStrategy Error Handling
# ============================================================================


class TestAssetStrategyErrorHandling:
    """Test error handling in AssetStrategy."""

    def test_get_price_timeseries_missing_symbol(self, sample_prices):
        """Test get_price_timeseries raises error if symbol not in prices."""
        asset = AssetStrategy('NONEXISTENT', currency='GBP')

        context = StrategyContext(
            current_date=datetime(2023, 6, 15),
            lookback_start=datetime(2023, 6, 1),
            prices=sample_prices.loc['2023-06-01':'2023-06-15']
        )

        with pytest.raises(ValueError, match="Symbol NONEXISTENT not in price data"):
            asset.get_price_timeseries(context)


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for core architecture."""

    def test_multiple_assets_with_requirements(self):
        """Test creating multiple asset strategies and their requirements."""
        assets = [
            AssetStrategy('VUSA', currency='GBP'),
            AssetStrategy('SSLN', currency='GBP'),
            AssetStrategy('SGLN', currency='GBP'),
            AssetStrategy('IWRD', currency='GBP'),
        ]

        # Collect requirements
        all_symbols = []
        for asset in assets:
            req = asset.get_data_requirements()
            all_symbols.extend(req.symbols)

        assert all_symbols == ['VUSA', 'SSLN', 'SGLN', 'IWRD']

    def test_context_with_portfolio_values(self, sample_prices):
        """Test StrategyContext can carry portfolio values for overlays."""
        portfolio_values = pd.Series(
            np.linspace(10000, 12000, len(sample_prices)),
            index=sample_prices.index
        )

        context = StrategyContext(
            current_date=datetime(2023, 6, 15),
            lookback_start=datetime(2023, 6, 1),
            prices=sample_prices.loc['2023-06-01':'2023-06-15'],
            portfolio_values=portfolio_values
        )

        assert context.portfolio_values is not None
        assert len(context.portfolio_values) > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
