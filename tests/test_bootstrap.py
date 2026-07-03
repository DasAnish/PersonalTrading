"""Tests for analytics/bootstrap.py and analytics/spa.py."""

import numpy as np
import pandas as pd
import pytest

from analytics.bootstrap import (
    BlockBootstrap,
    BootstrapResult,
    stationary_bootstrap_indices,
)
from analytics.spa import compute_spa

# --------------------------------------------------------------------------- #
# Stationary bootstrap primitive
# --------------------------------------------------------------------------- #


def test_indices_deterministic_with_seed():
    a = stationary_bootstrap_indices(200, 5, 50, np.random.default_rng(7))
    b = stationary_bootstrap_indices(200, 5, 50, np.random.default_rng(7))
    assert np.array_equal(a, b)


def test_indices_shape_and_range():
    idx = stationary_bootstrap_indices(120, 4, 30, np.random.default_rng(0))
    assert idx.shape == (30, 120)
    assert idx.min() >= 0 and idx.max() < 120


def test_mean_block_length_approximates_expected():
    """Average run length of contiguous blocks ≈ expected_block."""
    t, expected = 500, 8.0
    idx = stationary_bootstrap_indices(t, expected, 200, np.random.default_rng(3))
    # A "restart" is a step where the next index is not (cur + 1) % t.
    restarts = 0
    for row in idx:
        for j in range(t - 1):
            if row[j + 1] != (row[j] + 1) % t:
                restarts += 1
    n_blocks = restarts + idx.shape[0]  # +1 block per replication
    mean_block = idx.size / n_blocks
    assert expected * 0.7 <= mean_block <= expected * 1.3


def test_invalid_params():
    with pytest.raises(ValueError):
        stationary_bootstrap_indices(0, 5, 10, np.random.default_rng(0))
    with pytest.raises(ValueError):
        stationary_bootstrap_indices(100, 0.5, 10, np.random.default_rng(0))


# --------------------------------------------------------------------------- #
# BlockBootstrap (fast mode)
# --------------------------------------------------------------------------- #


def test_fast_bootstrap_distribution_shape():
    r = pd.Series(np.random.default_rng(0).normal(0.005, 0.02, 120))
    res = BlockBootstrap(n_iter=200, block_months=3, seed=1).run_fast(r)
    assert isinstance(res, BootstrapResult)
    assert len(res.sharpe) == 200
    d = res.to_dict()
    assert set(d["sharpe"]) >= {"dist", "mean", "median", "pct5", "pct95"}
    assert "sharpe" in d["realized"]


def test_fast_bootstrap_deterministic():
    r = pd.Series(np.random.default_rng(0).normal(0.005, 0.02, 120))
    a = BlockBootstrap(n_iter=100, seed=5).run_fast(r).sharpe
    b = BlockBootstrap(n_iter=100, seed=5).run_fast(r).sharpe
    assert a == b


def test_fast_bootstrap_too_few_obs():
    with pytest.raises(ValueError):
        BlockBootstrap().run_fast(pd.Series([0.01, 0.02, -0.01]))


# --------------------------------------------------------------------------- #
# SPA / Reality Check power
# --------------------------------------------------------------------------- #


def _spa_dataset(with_alpha: bool, seed: int = 42):
    rng = np.random.default_rng(seed)
    t, n = 240, 20
    bench = pd.Series(rng.normal(0.004, 0.02, t))
    cols = bench.values[:, None] + rng.normal(0, 0.01, (t, n))
    df = pd.DataFrame(cols, columns=[f"s{i}" for i in range(n)])
    if with_alpha:
        df["s0"] = bench.values + 0.010 + rng.normal(0, 0.01, t)
    return df, bench


def test_spa_rejects_true_alpha():
    df, bench = _spa_dataset(with_alpha=True)
    res = compute_spa(df, bench, expected_block=3, n_iter=500, seed=1)
    assert res.best_strategy == "s0"
    assert res.reality_check_pvalue < 0.05
    assert res.spa_pvalue_consistent < 0.05


def test_spa_does_not_reject_noise():
    df, bench = _spa_dataset(with_alpha=False)
    res = compute_spa(df, bench, expected_block=3, n_iter=500, seed=1)
    assert res.reality_check_pvalue > 0.10
    assert res.spa_pvalue_consistent > 0.10


def test_spa_result_serializable():
    import json
    import math

    df, bench = _spa_dataset(with_alpha=True)
    res = compute_spa(df, bench, expected_block=3, n_iter=200, seed=1)
    s = json.dumps(res.to_dict())
    assert "Infinity" not in s and "NaN" not in s
