"""
Regression tests for LongTermReversalStrategy's adaptive formation window.

The full asset universe's common history is capped by its youngest ETF, which
can fall just short of a 48-month formation window and starve every rebalance
(1 rebalance, None metrics). The strategy now uses the longest window that fits,
down to a MIN_FORMATION_MONTHS floor.
"""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from strategies.core import AssetStrategy, StrategyContext
from strategies.long_term_reversal import LongTermReversalStrategy

SYMBOLS = ["VUSA", "SSLN", "SGLN", "IWRD"]


def _assets():
    return [AssetStrategy(s, currency="GBP") for s in SYMBOLS]


def _prices(n_days: int, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2016-01-04", periods=n_days)
    # Distinct drifts so ranking (bottom_n = worst) is well-defined.
    drifts = {"VUSA": 0.0008, "SSLN": 0.0002, "SGLN": -0.0004, "IWRD": -0.0008}
    return pd.DataFrame(
        {
            s: 100.0 * np.cumprod(1 + rng.normal(mu, 0.008, n_days))
            for s, mu in drifts.items()
        },
        index=dates,
    )


def _ctx(prices: pd.DataFrame) -> StrategyContext:
    return StrategyContext(
        current_date=prices.index[-1], lookback_start=prices.index[0], prices=prices
    )


def _run(prices: pd.DataFrame, formation=48, bottom_n=2) -> pd.Series:
    strat = LongTermReversalStrategy(
        _assets(), formation_window_months=formation, bottom_n=bottom_n
    )
    return strat.calculate_weights(_ctx(prices))


class TestAdaptiveFormationWindow:
    def test_full_window_when_history_ample(self):
        # >48 months of history -> uses the full formation window, valid weights.
        w = _run(_prices(48 * 21 + 100))
        assert abs(w.sum() - 1.0) < 1e-9
        assert (w > 0).sum() == 2  # bottom_n held equal-weighted

    def test_adapts_when_history_between_floor_and_full(self):
        # ~30 months (< 48m requested, > 24m floor) must still produce weights
        # rather than raising — this is the case that used to starve rebalances.
        w = _run(_prices(30 * 21))
        assert abs(w.sum() - 1.0) < 1e-9
        assert (w > 0).sum() == 2

    def test_raises_below_floor(self):
        # < MIN_FORMATION_MONTHS of history is refused (not silently degraded).
        with pytest.raises(ValueError, match="Insufficient data"):
            _run(_prices(LongTermReversalStrategy.MIN_FORMATION_MONTHS * 21 - 20))

    def test_requirement_declares_full_window(self):
        # get_data_requirements must still request the full window so the runner
        # feeds enough history when it exists.
        strat = LongTermReversalStrategy(_assets(), formation_window_months=48)
        assert strat.get_data_requirements().lookback_days == 48 * 21
