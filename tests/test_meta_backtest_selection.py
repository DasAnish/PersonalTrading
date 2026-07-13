"""Tests for the selection-rule meta-backtest (scripts/meta_backtest_selection.py)."""

import numpy as np
import pandas as pd
import pytest

import scripts.meta_backtest_selection as M


def _histories(n_strategies=10, days=760, seed=0):
    """Synthetic daily NAVs: strategy i has a persistent drift rank."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2022-01-03", periods=days)
    out = {}
    for i in range(n_strategies):
        drift = 0.0008 * (i - n_strategies / 2)  # persistent winners/losers
        noise = rng.normal(0, 0.004, days)
        rets = drift + noise
        out[f"s{i:02d}"] = pd.Series(100.0 * np.cumprod(1.0 + rets), index=idx)
    return out


def test_structure_and_quarters():
    res = M.run_meta_backtest(_histories(), k=3, n_random=50)
    assert res["params"]["k"] == 3
    assert len(res["params"]["quarters"]) >= 3
    for block in ("selection", "hold_all"):
        assert res[block]["total_return"] is not None
        assert res[block]["n_quarters"] >= 3
    assert res["random"]["n_samples"] == 50
    assert 0.0 <= res["selection_percentile_vs_random"] <= 100.0


def test_deterministic_same_seed():
    h = _histories()
    a = M.run_meta_backtest(h, k=3, n_random=40, seed=7)
    b = M.run_meta_backtest(h, k=3, n_random=40, seed=7)
    assert a == b


def test_selection_beats_random_when_momentum_persists():
    # Persistent winners -> top-k by trailing Sharpe should land above the
    # median random pick.
    res = M.run_meta_backtest(_histories(seed=1), k=3, n_random=200, seed=99)
    assert res["selection_percentile_vs_random"] >= 50.0


def test_too_few_strategies_raises():
    with pytest.raises(ValueError):
        M.run_meta_backtest(_histories(n_strategies=3), k=5)


def test_quarter_return_asof():
    idx = pd.to_datetime(["2022-01-03", "2022-02-01", "2022-03-31"])
    s = pd.Series([100.0, 110.0, 121.0], index=idx)
    r = M._quarter_return(s, pd.Timestamp("2022-01-03"), pd.Timestamp("2022-03-31"))
    assert r == pytest.approx(0.21)
