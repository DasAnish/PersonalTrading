"""
Tests for the robustness guards added to strategies and portfolio state:
- MomentumTopNStrategy raises ValueError on too little data (no silent
  equal-weight fallback)
- MinimumVarianceStrategy applies ridge regularization on a near-singular
  covariance matrix instead of raising or misbehaving
- hrp.get_quasi_diag raises ValueError on an empty/None linkage matrix
- PortfolioState.execute_rebalance raises TypeError on non-Series input
"""

import logging
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from strategies.core import AssetStrategy, StrategyContext
from strategies.momentum import MomentumTopNStrategy
from strategies.minimum_variance import MinimumVarianceStrategy
from strategies.hrp import get_quasi_diag
from backtesting.portfolio_state import PortfolioState

SYMBOLS = ["VUSA", "SSLN"]


def _assets():
    return [AssetStrategy(s, currency="GBP") for s in SYMBOLS]


def _make_context(prices: pd.DataFrame) -> StrategyContext:
    return StrategyContext(
        current_date=prices.index[-1],
        lookback_start=prices.index[0],
        prices=prices,
    )


class TestMomentumInsufficientData:
    def test_raises_valueerror_on_too_few_rows(self):
        """Momentum must raise (not silently equal-weight) when data is short."""
        strategy = MomentumTopNStrategy(
            underlying=_assets(), top_n=2, lookback_days=252
        )

        # Only 30 rows, far fewer than min_required = max(30, 252) = 252
        rng = np.random.default_rng(0)
        dates = pd.bdate_range("2022-01-01", periods=30)
        prices = pd.DataFrame(
            {s: 100 * np.cumprod(1 + rng.normal(0, 0.01, 30)) for s in SYMBOLS},
            index=dates,
        )
        context = _make_context(prices)

        with pytest.raises(ValueError, match="Insufficient data for momentum"):
            strategy.calculate_weights(context)


class TestMinimumVarianceRidge:
    def test_ridge_applied_on_near_singular_cov_without_raising(self, caplog):
        """Two near-identical asset series produce an ill-conditioned covariance
        matrix; the strategy should apply ridge regularization and still return
        valid weights instead of raising or blowing up."""
        rng = np.random.default_rng(1)
        dates = pd.bdate_range("2020-01-01", periods=100)
        base_returns = rng.normal(0.0005, 0.01, 100)
        base_prices = 100 * np.cumprod(1 + base_returns)

        # SSLN tracks VUSA almost exactly (tiny epsilon noise) -> near-singular cov
        prices = pd.DataFrame(
            {
                "VUSA": base_prices,
                "SSLN": base_prices * (1 + 1e-12),
            },
            index=dates,
        )
        strategy = MinimumVarianceStrategy(underlying=_assets())
        context = _make_context(prices)

        with caplog.at_level(logging.WARNING):
            weights = strategy.calculate_weights(context)

        assert np.isclose(weights.sum(), 1.0, atol=1e-6)
        assert (weights >= -1e-9).all()
        assert any("ill-conditioned" in r.message for r in caplog.records)


class TestHRPEmptyLinkage:
    def test_get_quasi_diag_raises_on_none(self):
        with pytest.raises(ValueError, match="Empty linkage matrix"):
            get_quasi_diag(None)

    def test_get_quasi_diag_raises_on_empty_array(self):
        with pytest.raises(ValueError, match="Empty linkage matrix"):
            get_quasi_diag(np.array([]))


class TestPortfolioStateTypeGuards:
    def _portfolio(self):
        return PortfolioState(
            timestamp=datetime(2020, 1, 1), cash=10_000, positions={}, prices={}
        )

    def test_raises_typeerror_on_dict_target_weights(self):
        portfolio = self._portfolio()
        prices = pd.Series({"VUSA": 100.0})
        with pytest.raises(TypeError, match="target_weights"):
            portfolio.execute_rebalance(target_weights={"VUSA": 1.0}, prices=prices)

    def test_raises_typeerror_on_dataframe_prices(self):
        portfolio = self._portfolio()
        target_weights = pd.Series({"VUSA": 1.0})
        bad_prices = pd.DataFrame({"VUSA": [100.0]})
        with pytest.raises(TypeError, match="prices"):
            portfolio.execute_rebalance(
                target_weights=target_weights, prices=bad_prices
            )
