"""
End-to-end backtest tests using simulated price data.

Covers:
  - test_loader_builds_all_json_definitions  (fast, no mark)
  - test_equal_weight_nonzero_returns        (slow)
  - test_trend_following_differs_from_equal_weight (slow)
"""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path

from strategies.strategy_loader import StrategyLoader
from backtesting import BacktestEngine
from scripts.run_backtest import _run_single_backtest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_simulated_prices(n_days: int = 1000, seed: int = 42) -> pd.DataFrame:
    """
    Build a deterministic price DataFrame for 4 UK ETF symbols.

    Asset characteristics (chosen so trend_following has a clear signal):
      VUSA  strong upward trend   mean=+0.001/day, σ=0.01
      SSLN  weak upward trend     mean=+0.0003/day, σ=0.01
      SGLN  downward trend        mean=-0.0005/day, σ=0.01
      IWRD  flat                  mean=+0.0001/day, σ=0.01
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2019-01-02", periods=n_days)
    means = {"VUSA": 0.001, "SSLN": 0.0003, "SGLN": -0.0005, "IWRD": 0.0001}
    prices = {}
    for symbol, mu in means.items():
        daily_returns = rng.normal(mu, 0.01, n_days)
        prices[symbol] = 100.0 * np.cumprod(1 + daily_returns)
    return pd.DataFrame(prices, index=dates)


def _make_engine():
    return BacktestEngine(
        initial_capital=10_000,
        transaction_cost_bps=7.5,
        rebalance_frequency="monthly",
    )


# ---------------------------------------------------------------------------
# Fast test: loader can build every JSON definition without error
# ---------------------------------------------------------------------------

# Collect all JSON stems that are buildable (allocation / composed / asset)
_LOADER = StrategyLoader()
_BUILDABLE_STEMS = [
    stem
    for stem, path in {
        f.stem: f
        for f in (Path(__file__).parent.parent / "strategy_definitions").rglob("*.json")
    }.items()
    if _LOADER._load_file(
        next(
            (Path(__file__).parent.parent / "strategy_definitions").rglob(f"{stem}.json")
        )
    ).get("type")
    in ("allocation", "composed", "asset")
]


@pytest.mark.parametrize("strategy_key", _BUILDABLE_STEMS)
def test_loader_builds_all_json_definitions(strategy_key):
    """Every allocation/composed/asset JSON definition must build without error."""
    loader = StrategyLoader()
    strategy = loader.build_strategy(strategy_key)
    assert strategy is not None


# ---------------------------------------------------------------------------
# Slow backtest tests
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_equal_weight_nonzero_returns():
    """
    Regression test for the lookback bug:
    EqualWeightStrategy must execute rebalances and produce non-zero returns.
    """
    prices = make_simulated_prices()
    loader = StrategyLoader()
    strategy = loader.build_strategy("equal_weight")
    engine = _make_engine()

    backtest_start = prices.index[252]
    backtest_end = prices.index[-1]

    results = _run_single_backtest(strategy, prices, backtest_start, backtest_end, engine)

    assert len(results.transactions) > 0, "EqualWeight made zero transactions"
    assert len(results.portfolio_history) > 1, "EqualWeight produced no portfolio history"
    total_return = (results.final_value - 10_000) / 10_000
    assert total_return != 0.0, "EqualWeight total return is exactly zero"


@pytest.mark.slow
def test_trend_following_differs_from_equal_weight():
    """
    Regression test for the fallback bug:
    TrendFollowingStrategy must produce weights that differ from 0.25 equal-weight
    on at least one rebalance date.
    """
    prices = make_simulated_prices()
    loader = StrategyLoader()
    tf_strategy = loader.build_strategy("trend_following")
    engine = _make_engine()

    backtest_start = prices.index[252]
    backtest_end = prices.index[-1]

    results = _run_single_backtest(tf_strategy, prices, backtest_start, backtest_end, engine)

    assert not results.weights_history.empty, "TrendFollowing produced no weights history"

    # Check that at least one rebalance has a weight deviating > 1% from 0.25
    max_deviation = (results.weights_history - 0.25).abs().max().max()
    assert max_deviation > 0.01, (
        f"TrendFollowing weights never deviated from equal-weight by more than 1% "
        f"(max deviation: {max_deviation:.4f}). Likely still falling back to equal-weight."
    )
