"""Tests for analytics/cpcv.py — Combinatorial Purged Cross-Validation."""

from math import comb

import numpy as np
import pandas as pd
import pytest

from analytics.cpcv import CPCVEngine, CPCVResult, _verdict


def _returns(n: int = 240, seed: int = 0) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(rng.normal(0.005, 0.02, n))


def test_combination_count_is_c_k_2():
    res = CPCVEngine(n_groups=6, n_test_groups=2, embargo_days=0).run(_returns())
    assert res.n_combinations == comb(6, 2) == 15
    assert len(res.oos_sharpes) == 15


def test_combination_count_scales():
    res = CPCVEngine(n_groups=5, n_test_groups=2, embargo_days=0).run(_returns())
    assert res.n_combinations == comb(5, 2) == 10


def test_no_lookahead_property():
    """Mutating one group's data changes only the combinations that include it."""
    r = _returns()
    engine = CPCVEngine(n_groups=6, n_test_groups=2, embargo_days=0)
    base = engine.run(r)

    # Corrupt group 0's observations only (folds discard the residual, so with
    # 240/6=40 evenly divisible there is no residual; group 0 = indices 0..40).
    r2 = r.copy()
    r2.iloc[0:40] = r2.iloc[0:40] * 5.0 + 1.0

    mutated = engine.run(r2)
    differing = sum(
        1 for a, b in zip(base.oos_sharpes, mutated.oos_sharpes) if abs(a - b) > 1e-9
    )
    # Combinations that include group 0 = C(5, 1) = 5.
    assert differing == comb(5, 1) == 5


def test_embargo_changes_distribution():
    """A non-zero embargo (large enough to be >=1 period) alters the result."""
    r = _returns(n=360)
    no_embargo = CPCVEngine(n_groups=6, n_test_groups=2, embargo_days=0).run(r)
    # 90 calendar days at monthly periodicity -> round(90*12/365.25)=3 periods.
    embargoed = CPCVEngine(n_groups=6, n_test_groups=2, embargo_days=90).run(r)
    assert embargoed.embargo_periods >= 1
    assert no_embargo.oos_sharpes != embargoed.oos_sharpes


def test_summary_stats_shape():
    res = CPCVEngine(n_groups=6, n_test_groups=2, embargo_days=0).run(_returns())
    assert isinstance(res, CPCVResult)
    assert 0.0 <= res.prob_oos_sharpe_positive <= 1.0
    assert res.pct5_sharpe <= res.median_sharpe + 1e-9
    d = res.to_dict()
    for key in (
        "oos_sharpes",
        "mean_sharpe",
        "pct5_sharpe",
        "prob_oos_sharpe_positive",
        "verdict",
        "n_combinations",
    ):
        assert key in d
    assert d["verdict"] in ("PASS", "WARN", "FAIL")


def test_verdict_thresholds():
    assert _verdict(0.95, 0.0) == "PASS"
    assert _verdict(0.9, -0.4) == "PASS"
    assert _verdict(0.9, -0.6) == "WARN"  # pct5 too low -> not PASS
    assert _verdict(0.75, -2.0) == "WARN"
    assert _verdict(0.5, 1.0) == "FAIL"


def test_invalid_config():
    with pytest.raises(ValueError):
        CPCVEngine(n_groups=1)
    with pytest.raises(ValueError):
        CPCVEngine(n_groups=6, n_test_groups=6)
    with pytest.raises(ValueError):
        CPCVEngine(n_groups=6, n_test_groups=0)


def test_too_few_observations():
    with pytest.raises(ValueError):
        CPCVEngine(n_groups=6, n_test_groups=2).run(_returns(n=10))
