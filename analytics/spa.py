"""
Data-snooping tests: White's Reality Check and Hansen's SPA.

When many strategies are mined over the same data, the best one's performance is
upward-biased by selection. White's Reality Check (2000) and Hansen's Superior
Predictive Ability test (2005) give a p-value for the null "no strategy in the
set beats the benchmark", correcting for the full set of trials.

Both operate on loss/performance differentials ``d_{l,t} = r_{l,t} - r_{bench,t}``
(strategy return minus benchmark return, per period) and use the stationary
bootstrap from ``analytics.bootstrap`` to build the null distribution. Hansen's
SPA studentizes and recenters, which makes it more powerful than the RC when the
set contains many poor strategies.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pandas as pd

from analytics.bootstrap import stationary_bootstrap_indices

logger = logging.getLogger(__name__)


@dataclass
class SPAResult:
    """Reality Check + SPA p-values for a set of strategies vs a benchmark."""

    strategy_names: List[str]
    best_strategy: str
    reality_check_pvalue: float
    spa_pvalue_lower: float
    spa_pvalue_consistent: float
    spa_pvalue_upper: float
    n_strategies: int
    n_obs: int
    n_iter: int
    expected_block: float

    def to_dict(self) -> dict:
        def _p(x: float) -> Optional[float]:
            return None if x is None or not math.isfinite(x) else round(x, 4)

        return {
            "best_strategy": self.best_strategy,
            "reality_check_pvalue": _p(self.reality_check_pvalue),
            "spa_pvalue_lower": _p(self.spa_pvalue_lower),
            "spa_pvalue_consistent": _p(self.spa_pvalue_consistent),
            "spa_pvalue_upper": _p(self.spa_pvalue_upper),
            "n_strategies": self.n_strategies,
            "n_obs": self.n_obs,
            "n_iter": self.n_iter,
            "expected_block": self.expected_block,
        }


def compute_spa(
    returns_matrix: pd.DataFrame,
    benchmark: pd.Series,
    expected_block: float = 3.0,
    n_iter: int = 1000,
    seed: int = 0,
) -> SPAResult:
    """
    White's Reality Check and Hansen's SPA over a strategy return matrix.

    Args:
        returns_matrix: (T, N) per-period strategy returns (columns = strategies).
        benchmark: (T,) per-period benchmark returns, aligned to the matrix index.
        expected_block: mean stationary-bootstrap block length (periods).
        n_iter: bootstrap replications.
        seed: RNG seed for determinism.

    Returns:
        SPAResult with the RC p-value and Hansen's lower/consistent/upper SPA
        p-values. Small p-values reject "no strategy beats the benchmark".
    """
    aligned = returns_matrix.dropna(how="any")
    bench = benchmark.reindex(aligned.index).dropna()
    aligned = aligned.reindex(bench.index)
    d = aligned.sub(bench, axis=0)  # (T, N) differentials

    t, n = d.shape
    if t < 12 or n < 1:
        raise ValueError(f"Need >= 12 obs and >= 1 strategy, got T={t}, N={n}")

    d_vals = d.values  # (T, N)
    mean_d = d_vals.mean(axis=0)  # (N,)
    root_t = math.sqrt(t)
    f_bar = root_t * mean_d  # (N,) RC statistic components

    rng = np.random.default_rng(seed)
    idx = stationary_bootstrap_indices(t, expected_block, n_iter, rng)  # (B, T)

    # Bootstrap means for every replication and column: (B, N)
    boot_means = np.stack([d_vals[idx[b]].mean(axis=0) for b in range(n_iter)])

    # --- Bootstrap variance estimate omega_l (Hansen studentization) ---
    # var of sqrt(T)*mean over bootstrap replications.
    z = root_t * (boot_means - mean_d[None, :])  # (B, N), recentered
    omega = z.std(axis=0, ddof=1)  # (N,)
    omega = np.where(omega < 1e-8, 1e-8, omega)

    # --- White's Reality Check ---
    v_obs = float(np.max(f_bar))
    v_boot = (root_t * (boot_means - mean_d[None, :])).max(axis=1)  # (B,)
    rc_p = float(np.mean(v_boot >= v_obs))

    # --- Hansen's SPA (studentized) ---
    t_stat = f_bar / omega  # (N,)
    spa_obs = max(0.0, float(np.max(t_stat)))

    # Recentering thresholds for the three variants (Hansen 2005).
    a_n = math.sqrt(2.0 * math.log(math.log(t))) if t > math.e else 0.0
    # consistent: keep model's own mean only if it is sufficiently poor.
    # Recenter unless the model is clearly inferior (Hansen 2005 consistent
    # estimator); non-negative models get recentered too so a genuine winner
    # is detected. upper recenters all; lower recenters only non-negative means.
    g_consistent = np.where((root_t * mean_d / omega) >= -a_n, mean_d, 0.0)
    # lower: recenter only non-positive means; upper: recenter all.
    g_lower = np.where(mean_d >= 0.0, mean_d, 0.0)
    g_upper = mean_d

    def _spa_p(g: np.ndarray) -> float:
        z_boot = root_t * (boot_means - g[None, :]) / omega[None, :]  # (B, N)
        stat_boot = np.maximum(0.0, z_boot.max(axis=1))  # (B,)
        return float(np.mean(stat_boot >= spa_obs))

    spa_lower = _spa_p(g_lower)
    spa_consistent = _spa_p(g_consistent)
    spa_upper = _spa_p(g_upper)

    best = str(aligned.columns[int(np.argmax(mean_d))])
    return SPAResult(
        strategy_names=list(aligned.columns),
        best_strategy=best,
        reality_check_pvalue=rc_p,
        spa_pvalue_lower=spa_lower,
        spa_pvalue_consistent=spa_consistent,
        spa_pvalue_upper=spa_upper,
        n_strategies=n,
        n_obs=t,
        n_iter=n_iter,
        expected_block=expected_block,
    )
