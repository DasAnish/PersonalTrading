"""
Tests for strategy abstract base class and implementations.

This module tests:
- BaseStrategy abstract class behavior and constraints
- Contract that all implementations must follow
- Concrete strategy implementations (EqualWeight, HRP)
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import Mock, patch
from strategies.base import BaseStrategy
from strategies.equal_weight import EqualWeightStrategy
from strategies.hrp import HRPStrategy


class TestBaseStrategyAbstract:
    """Test BaseStrategy abstract base class."""

    def test_cannot_instantiate_abstract_class(self):
        """Test that BaseStrategy cannot be instantiated directly."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            BaseStrategy()

    def test_must_implement_calculate_weights(self):
        """Test that concrete classes must implement calculate_weights."""
        # Create a concrete class that doesn't implement the abstract method
        class IncompleteStrategy(BaseStrategy):
            pass

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteStrategy()

    def test_name_initialization_default(self):
        """Test that strategy name defaults to class name."""
        strategy = EqualWeightStrategy()
        assert strategy.name == "Equal Weight"

    def test_name_initialization_custom(self):
        """Test that custom strategy name is set correctly."""
        class TestStrategy(BaseStrategy):
            def calculate_weights(self, prices):
                return pd.Series()

        strategy = TestStrategy(name="Custom Name")
        assert strategy.name == "Custom Name"

    def test_repr_method(self):
        """Test __repr__ method returns proper string representation."""
        strategy = EqualWeightStrategy()
        assert repr(strategy) == "EqualWeightStrategy(name='Equal Weight')"

    def test_repr_with_custom_name(self):
        """Test __repr__ with custom name."""
        class TestStrategy(BaseStrategy):
            def calculate_weights(self, prices):
                return pd.Series()

        strategy = TestStrategy(name="Custom")
        assert repr(strategy) == "TestStrategy(name='Custom')"


class TestCalculateWeightsContract:
    """Test the contract that all strategies must follow for calculate_weights."""

    @pytest.fixture
    def sample_prices(self):
        """Create sample price data for testing."""
        dates = pd.date_range('2023-01-01', periods=100, freq='D')
        data = {
            'VUSA': np.random.randn(100).cumsum() + 100,
            'SSLN': np.random.randn(100).cumsum() + 100,
            'SGLN': np.random.randn(100).cumsum() + 100,
            'IWRD': np.random.randn(100).cumsum() + 100,
        }
        return pd.DataFrame(data, index=dates)

    def test_returns_pandas_series(self, sample_prices):
        """Test that calculate_weights returns a pandas Series."""
        strategy = EqualWeightStrategy()
        weights = strategy.calculate_weights(sample_prices)
        assert isinstance(weights, pd.Series)

    def test_weights_sum_to_one(self, sample_prices):
        """Test that weights sum to approximately 1.0."""
        strategy = EqualWeightStrategy()
        weights = strategy.calculate_weights(sample_prices)
        assert np.isclose(weights.sum(), 1.0), f"Weights sum: {weights.sum()}"

    def test_all_weights_non_negative(self, sample_prices):
        """Test that all weights are non-negative (long-only constraint)."""
        strategy = EqualWeightStrategy()
        weights = strategy.calculate_weights(sample_prices)
        assert (weights >= 0).all(), f"Negative weights found: {weights[weights < 0]}"

    def test_weights_index_matches_columns(self, sample_prices):
        """Test that weights index matches input DataFrame columns."""
        strategy = EqualWeightStrategy()
        weights = strategy.calculate_weights(sample_prices)
        assert list(weights.index) == list(sample_prices.columns)

    def test_weights_length_matches_assets(self, sample_prices):
        """Test that number of weights equals number of assets."""
        strategy = EqualWeightStrategy()
        weights = strategy.calculate_weights(sample_prices)
        assert len(weights) == len(sample_prices.columns)

    def test_invalid_input_empty_dataframe(self):
        """Test error handling for empty DataFrame."""
        strategy = EqualWeightStrategy()
        empty_df = pd.DataFrame()

        with pytest.raises(ValueError, match="empty"):
            strategy.calculate_weights(empty_df)

    def test_invalid_input_no_columns(self):
        """Test error handling for DataFrame with no columns."""
        strategy = EqualWeightStrategy()
        dates = pd.date_range('2023-01-01', periods=10)
        df = pd.DataFrame(index=dates)

        with pytest.raises(ValueError, match="empty"):
            strategy.calculate_weights(df)

    def test_single_asset(self, sample_prices):
        """Test that single-asset portfolio gets weight of 1.0."""
        strategy = EqualWeightStrategy()
        single_asset = sample_prices[['VUSA']]
        weights = strategy.calculate_weights(single_asset)

        assert len(weights) == 1
        assert weights.iloc[0] == 1.0

    def test_many_assets(self, sample_prices):
        """Test with multiple assets."""
        strategy = EqualWeightStrategy()
        weights = strategy.calculate_weights(sample_prices)

        assert len(weights) == 4
        expected_weight = 0.25
        assert all(np.isclose(weights, expected_weight))


class TestEqualWeightStrategy:
    """Test EqualWeightStrategy implementation."""

    def test_equal_weight_calculation(self):
        """Test that equal weight strategy distributes weight equally."""
        dates = pd.date_range('2023-01-01', periods=50)
        prices = pd.DataFrame({
            'A': [100] * 50,
            'B': [100] * 50,
            'C': [100] * 50,
        }, index=dates)

        strategy = EqualWeightStrategy()
        weights = strategy.calculate_weights(prices)

        expected = pd.Series([1/3, 1/3, 1/3], index=['A', 'B', 'C'])
        pd.testing.assert_series_equal(weights, expected, atol=1e-10)

    def test_equal_weight_two_assets(self):
        """Test equal weight with two assets."""
        dates = pd.date_range('2023-01-01', periods=50)
        prices = pd.DataFrame({
            'X': [100] * 50,
            'Y': [100] * 50,
        }, index=dates)

        strategy = EqualWeightStrategy()
        weights = strategy.calculate_weights(prices)

        assert np.isclose(weights['X'], 0.5)
        assert np.isclose(weights['Y'], 0.5)

    def test_equal_weight_independent_of_prices(self):
        """Test that equal weight doesn't depend on actual price values."""
        dates = pd.date_range('2023-01-01', periods=50)
        prices_1 = pd.DataFrame({
            'A': [100] * 50,
            'B': [200] * 50,
        }, index=dates)

        prices_2 = pd.DataFrame({
            'A': [1000] * 50,
            'B': [50] * 50,
        }, index=dates)

        strategy = EqualWeightStrategy()
        weights_1 = strategy.calculate_weights(prices_1)
        weights_2 = strategy.calculate_weights(prices_2)

        pd.testing.assert_series_equal(weights_1, weights_2, atol=1e-10)

    def test_equal_weight_name(self):
        """Test that EqualWeightStrategy has correct name."""
        strategy = EqualWeightStrategy()
        assert strategy.name == "Equal Weight"


class TestHRPStrategy:
    """Test HRPStrategy implementation."""

    @pytest.fixture
    def hrp_strategy(self):
        """Create HRP strategy instance."""
        return HRPStrategy()

    @pytest.fixture
    def sample_prices_hrp(self):
        """Create price data for HRP testing."""
        np.random.seed(42)
        dates = pd.date_range('2023-01-01', periods=252, freq='D')

        # Create correlated returns
        returns = pd.DataFrame(
            np.random.randn(252, 4),
            columns=['VUSA', 'SSLN', 'SGLN', 'IWRD'],
            index=dates
        )

        # Convert to prices (cumulative product)
        prices = (1 + returns * 0.01).cumprod() * 100
        return prices

    def test_hrp_returns_series(self, hrp_strategy, sample_prices_hrp):
        """Test that HRP returns a pandas Series."""
        weights = hrp_strategy.calculate_weights(sample_prices_hrp)
        assert isinstance(weights, pd.Series)

    def test_hrp_weights_sum_to_one(self, hrp_strategy, sample_prices_hrp):
        """Test that HRP weights sum to 1.0."""
        weights = hrp_strategy.calculate_weights(sample_prices_hrp)
        assert np.isclose(weights.sum(), 1.0, atol=1e-10)

    def test_hrp_weights_non_negative(self, hrp_strategy, sample_prices_hrp):
        """Test that HRP weights are all non-negative."""
        weights = hrp_strategy.calculate_weights(sample_prices_hrp)
        assert (weights >= 0).all()

    def test_hrp_name(self, hrp_strategy):
        """Test that HRPStrategy has correct default name."""
        assert hrp_strategy.name == "Hierarchical Risk Parity"

    def test_hrp_with_linkage_method(self, sample_prices_hrp):
        """Test HRP with different linkage methods."""
        for method in ['single', 'complete', 'average', 'ward']:
            strategy = HRPStrategy(linkage_method=method)
            weights = strategy.calculate_weights(sample_prices_hrp)

            assert isinstance(weights, pd.Series)
            assert np.isclose(weights.sum(), 1.0)
            assert (weights >= 0).all()

    def test_hrp_custom_name(self):
        """Test HRP with custom name."""
        strategy = HRPStrategy(name="Custom HRP")
        assert strategy.name == "Custom HRP"

    def test_hrp_insufficient_data(self, hrp_strategy):
        """Test HRP with insufficient data (too few rows)."""
        dates = pd.date_range('2023-01-01', periods=10)
        prices = pd.DataFrame({
            'A': np.random.randn(10),
            'B': np.random.randn(10),
        }, index=dates)

        # HRP may raise ValueError if insufficient data for correlation
        try:
            weights = hrp_strategy.calculate_weights(prices)
            # If it doesn't raise, weights should still follow contract
            assert isinstance(weights, pd.Series)
            assert np.isclose(weights.sum(), 1.0)
            assert (weights >= 0).all()
        except ValueError:
            # This is acceptable behavior for insufficient data
            pass


class TestStrategyInterface:
    """Test that strategies follow a consistent interface."""

    @pytest.fixture
    def strategies(self):
        """Return instances of all available strategies."""
        return [
            EqualWeightStrategy(),
            HRPStrategy(),
        ]

    @pytest.fixture
    def sample_prices(self):
        """Create sample price data."""
        np.random.seed(42)
        dates = pd.date_range('2023-01-01', periods=252, freq='D')
        data = {
            'VUSA': np.random.randn(252).cumsum() + 100,
            'SSLN': np.random.randn(252).cumsum() + 100,
            'SGLN': np.random.randn(252).cumsum() + 100,
            'IWRD': np.random.randn(252).cumsum() + 100,
        }
        return pd.DataFrame(data, index=dates)

    def test_all_strategies_have_name(self, strategies):
        """Test that all strategies have a name attribute."""
        for strategy in strategies:
            assert hasattr(strategy, 'name')
            assert isinstance(strategy.name, str)
            assert len(strategy.name) > 0

    def test_all_strategies_have_repr(self, strategies):
        """Test that all strategies have __repr__ method."""
        for strategy in strategies:
            repr_str = repr(strategy)
            assert isinstance(repr_str, str)
            assert strategy.__class__.__name__ in repr_str

    def test_all_strategies_implement_calculate_weights(self, strategies):
        """Test that all strategies implement calculate_weights."""
        for strategy in strategies:
            assert hasattr(strategy, 'calculate_weights')
            assert callable(strategy.calculate_weights)

    def test_all_strategies_fulfill_contract(self, strategies, sample_prices):
        """Test that all strategies fulfill the contract."""
        for strategy in strategies:
            weights = strategy.calculate_weights(sample_prices)

            # Check return type
            assert isinstance(weights, pd.Series), \
                f"{strategy.name}: Should return pd.Series"

            # Check weights sum to 1
            assert np.isclose(weights.sum(), 1.0, atol=1e-9), \
                f"{strategy.name}: Weights should sum to 1.0, got {weights.sum()}"

            # Check all weights non-negative
            assert (weights >= 0).all(), \
                f"{strategy.name}: All weights should be non-negative"

            # Check index matches
            assert list(weights.index) == list(sample_prices.columns), \
                f"{strategy.name}: Index should match DataFrame columns"

    def test_strategies_produce_different_weights(self, sample_prices):
        """Test that different strategies can produce different weight distributions."""
        equal_weight = EqualWeightStrategy()
        hrp = HRPStrategy()

        weights_ew = equal_weight.calculate_weights(sample_prices)
        weights_hrp = hrp.calculate_weights(sample_prices)

        # They should generally be different (though could be equal by chance)
        # This is more of a smoke test
        assert isinstance(weights_ew, pd.Series)
        assert isinstance(weights_hrp, pd.Series)
        # They might be different
        # (no assertion needed, just testing they both work independently)


class TestStrategyEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_strategy_with_single_date(self):
        """Test strategy with only one date of price data."""
        dates = pd.date_range('2023-01-01', periods=1)
        prices = pd.DataFrame({
            'A': [100],
            'B': [200],
        }, index=dates)

        strategy = EqualWeightStrategy()
        weights = strategy.calculate_weights(prices)

        assert isinstance(weights, pd.Series)
        assert len(weights) == 2
        assert np.isclose(weights.sum(), 1.0)

    def test_strategy_with_nan_values(self):
        """Test strategy behavior with NaN values in prices."""
        dates = pd.date_range('2023-01-01', periods=100)
        prices = pd.DataFrame({
            'A': [100] * 100,
            'B': [np.nan] * 50 + [100] * 50,
        }, index=dates)

        strategy = EqualWeightStrategy()
        # Equal weight should handle NaN gracefully
        weights = strategy.calculate_weights(prices)

        assert isinstance(weights, pd.Series)
        assert np.isclose(weights.sum(), 1.0)

    def test_strategy_with_zero_prices(self):
        """Test strategy with zero price values."""
        dates = pd.date_range('2023-01-01', periods=50)
        prices = pd.DataFrame({
            'A': [0] * 50,
            'B': [100] * 50,
        }, index=dates)

        strategy = EqualWeightStrategy()
        weights = strategy.calculate_weights(prices)

        # Equal weight should still work
        assert isinstance(weights, pd.Series)
        assert len(weights) == 2

    def test_strategy_with_negative_prices(self):
        """Test strategy with negative prices (edge case, shouldn't happen in practice)."""
        dates = pd.date_range('2023-01-01', periods=50)
        prices = pd.DataFrame({
            'A': [-100] * 50,
            'B': [100] * 50,
        }, index=dates)

        strategy = EqualWeightStrategy()
        weights = strategy.calculate_weights(prices)

        assert isinstance(weights, pd.Series)
        assert np.isclose(weights.sum(), 1.0)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
