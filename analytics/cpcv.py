"""
Combinatorial Purged Cross-Validation (CPCV).

López de Prado's CPCV (*Advances in Financial Machine Learning*, ch. 12)
produces a distribution of out-of-sample performance across many
train/test recombinations rather than a single backtest number, which makes
path-dependent / lucky strategies visible.

Partition the observations into ``n_groups`` contiguous groups, then form
every ``C(n_groups, n_test_groups)`` combination of groups as an out-of-sample
test set. A purge + embargo buffer around each test window prevents adjacent
observations from leaking across the train/test boundary.

Important scope note: the strategies in this project have **no fitting step**
(weights are computed from a rolling lookback, not trained), so there is no
model to re-estimate per split. CPCV here therefore measures the
*path-robustness* of realised out-of-sample performance: for each combination
we evaluate the strategy's realised returns on that combination's test windows
(after purge+embargo) and collect the resulting Sharpe. Because only
test-window returns are ever read, the result of a combination is invariant to
data outside its test windows (the no-lookahead property the tests assert).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from itertools import combinations
from typing import List, Optional

import numpy as np
import pandas as pd

from analytics.metrics import calculate_sharpe_ratio
from optimization.splitters import contiguous_folds

logger = logging.getLogger(__name__)


@dataclass
class CPCVResult:
    """Out-of-sample Sharpe distribution from a CPCV run."""

    oos_sharpes: List[float]
    mean_sharpe: float
    median_sharpe: float
    pct5_sharpe: float  # 5th percentile (left-tail OOS Sharpe)
    prob_oos_sharpe_positive: float
    n_groups: int
    n_test_groups: int
    n_combinations: int
    embargo_periods: int
    verdict: str  # PASS / WARN / FAIL
    config: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        def _s(x: float) -> Optional[float]:
            return None if x is None or not math.isfinite(x) else round(x, 4)

        return {
            "oos_sharpes": [_s(x) for x in self.oos_sharpes],
            "mean_sharpe": _s(self.mean_sharpe),
            "median_sharpe": _s(self.median_sharpe),
            "pct5_sharpe": _s(self.pct5_sharpe),
            "prob_oos_sharpe_positive": _s(self.prob_oos_sharpe_positive),
            "n_groups": self.n_groups,
            "n_test_groups": self.n_test_groups,
            "n_combinations": self.n_combinations,
            "embargo_periods": self.embargo_periods,
            "verdict": self.verdict,
            "config": self.config,
        }


def _verdict(prob_positive: float, pct5: float) -> str:
    if prob_positive >= 0.9 and pct5 > -0.5:
        return "PASS"
    if prob_positive >= 0.7:
        return "WARN"
    return "FAIL"


class CPCVEngine:
    """
    Combinatorial Purged Cross-Validation over a realised return series.

    Args:
        n_groups: number of contiguous groups to partition observations into.
        n_test_groups: groups per test set (test combinations = C(n_groups, n_test_groups)).
        embargo_days: calendar days trimmed from each test-group inner edge
            (converted to periods via ``periods_per_year``).
        periods_per_year: 12 for monthly rebalancing (this project's default).
    """

    def __init__(
        self,
        n_groups: int = 6,
        n_test_groups: int = 2,
        embargo_days: int = 10,
        periods_per_year: int = 12,
    ) -> None:
        if n_groups < 2:
            raise ValueError("n_groups must be >= 2")
        if not 1 <= n_test_groups < n_groups:
            raise ValueError("n_test_groups must be in [1, n_groups)")
        self.n_groups = n_groups
        self.n_test_groups = n_test_groups
        self.embargo_days = embargo_days
        self.periods_per_year = periods_per_year
        self.embargo_periods = (
            round(embargo_days * periods_per_year / 365.25) if embargo_days else 0
        )

    def run(self, returns: pd.Series) -> CPCVResult:
        """Compute the OOS Sharpe distribution across all test-group combinations."""
        returns = returns.dropna()
        t = len(returns)
        if t < self.n_groups * 3:
            raise ValueError(
                f"Not enough observations ({t}) for {self.n_groups} groups "
                f"(need >= {self.n_groups * 3})."
            )

        groups = contiguous_folds(t, self.n_groups)  # list of (start, end)
        values = returns.values

        oos: List[float] = []
        for combo in combinations(range(self.n_groups), self.n_test_groups):
            idx: List[int] = []
            for g in combo:
                start, end = groups[g]
                # Embargo: trim embargo_periods rows from each inner edge of
                # the test group to avoid boundary contamination.
                e = self.embargo_periods
                lo = start + e
                hi = end - e
                if hi <= lo:
                    lo, hi = start, end  # group too small to embargo; use whole
                idx.extend(range(lo, hi))
            if len(idx) < 3:
                continue
            test_returns = pd.Series(values[idx])
            sharpe = calculate_sharpe_ratio(
                test_returns, periods_per_year=self.periods_per_year
            )
            if math.isfinite(sharpe):
                oos.append(float(sharpe))

        if not oos:
            raise ValueError("CPCV produced no valid test combinations.")

        arr = np.array(oos)
        mean_s = float(arr.mean())
        median_s = float(np.median(arr))
        pct5 = float(np.percentile(arr, 5))
        prob_pos = float((arr > 0).mean())

        return CPCVResult(
            oos_sharpes=oos,
            mean_sharpe=mean_s,
            median_sharpe=median_s,
            pct5_sharpe=pct5,
            prob_oos_sharpe_positive=prob_pos,
            n_groups=self.n_groups,
            n_test_groups=self.n_test_groups,
            n_combinations=len(oos),
            embargo_periods=self.embargo_periods,
            verdict=_verdict(prob_pos, pct5),
            config={
                "embargo_days": self.embargo_days,
                "periods_per_year": self.periods_per_year,
            },
        )
