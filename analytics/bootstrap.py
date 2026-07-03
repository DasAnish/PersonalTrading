"""
Stationary block bootstrap (Politis & Romano, 1994).

Resamples contiguous blocks of a return series with geometric (random) block
lengths, preserving short-range autocorrelation that an i.i.d. bootstrap would
destroy. Used to build robustness distributions for a strategy's performance
metrics, and as the resampling primitive behind the data-snooping tests in
``analytics/spa.py``.

Two evaluation paths:
- ``run_fast``: resample the strategy's *realised* returns directly (cheap; no
  backtests). Default for tests and interactive use.
- ``run``: resample the underlying price *returns* into synthetic price series
  and re-run the backtest each iteration (faithful but minutes-scale; ``slow``).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd

from analytics.metrics import (
    calculate_cagr,
    calculate_calmar_ratio,
    calculate_max_drawdown,
    calculate_sharpe_ratio,
)

logger = logging.getLogger(__name__)


def stationary_bootstrap_indices(
    t: int, expected_block: float, n_iter: int, rng: np.random.Generator
) -> np.ndarray:
    """
    Politis–Romano stationary bootstrap index matrix.

    Block lengths are geometric with mean ``expected_block``; at each step the
    resample either advances within the current block (prob ``1 - 1/L``) or
    jumps to a fresh random start (prob ``1/L``). Indices wrap around the end of
    the series so every observation is equally likely to appear.

    Args:
        t: length of the series being resampled.
        expected_block: mean block length (>= 1).
        n_iter: number of bootstrap replications.
        rng: a seeded ``numpy`` Generator (determinism is the caller's job).

    Returns:
        ``(n_iter, t)`` int array of indices into ``[0, t)``.
    """
    if t <= 0:
        raise ValueError("t must be positive")
    if expected_block < 1:
        raise ValueError("expected_block must be >= 1")

    p = 1.0 / expected_block
    out = np.empty((n_iter, t), dtype=np.int64)
    for i in range(n_iter):
        cur = int(rng.integers(0, t))
        row = out[i]
        jumps = rng.random(t)
        starts = rng.integers(0, t, size=t)
        for j in range(t):
            row[j] = cur
            if jumps[j] < p:
                cur = int(starts[j])
            else:
                cur = (cur + 1) % t
    return out


@dataclass
class BootstrapResult:
    """Distributions of performance metrics over bootstrap replications."""

    realized: dict  # realized metric values
    sharpe: List[float] = field(default_factory=list)
    calmar: List[float] = field(default_factory=list)
    max_drawdown: List[float] = field(default_factory=list)
    annual_return: List[float] = field(default_factory=list)
    n_iter: int = 0
    expected_block: float = 0.0
    mode: str = "fast"

    def _summary(self, arr: List[float]) -> dict:
        a = np.array([x for x in arr if math.isfinite(x)], dtype=float)
        if a.size == 0:
            return {"mean": None, "median": None, "pct5": None, "pct95": None}
        return {
            "mean": round(float(a.mean()), 4),
            "median": round(float(np.median(a)), 4),
            "pct5": round(float(np.percentile(a, 5)), 4),
            "pct95": round(float(np.percentile(a, 95)), 4),
        }

    def to_dict(self) -> dict:
        def _clean(vals: List[float]) -> List[float]:
            return [round(v, 4) for v in vals if math.isfinite(v)]

        return {
            "mode": self.mode,
            "n_iter": self.n_iter,
            "expected_block": self.expected_block,
            "realized": self.realized,
            "sharpe": {"dist": _clean(self.sharpe), **self._summary(self.sharpe)},
            "calmar": {"dist": _clean(self.calmar), **self._summary(self.calmar)},
            "max_drawdown": self._summary(self.max_drawdown),
            "annual_return": self._summary(self.annual_return),
        }


class BlockBootstrap:
    """Stationary block bootstrap over a strategy's returns or its price inputs."""

    def __init__(
        self,
        n_iter: int = 500,
        block_months: int = 3,
        periods_per_year: int = 12,
        seed: int = 0,
    ) -> None:
        self.n_iter = n_iter
        self.block_months = block_months
        self.periods_per_year = periods_per_year
        self.seed = seed
        # Expected block length in *periods* of the resampled series.
        self.expected_block = max(1.0, block_months * periods_per_year / 12.0)

    @staticmethod
    def _metrics_from_returns(returns: np.ndarray, periods_per_year: int) -> tuple:
        r = pd.Series(returns)
        sharpe = calculate_sharpe_ratio(r, periods_per_year=periods_per_year)
        values = (1.0 + r).cumprod()
        # Give the reconstructed value series a synthetic monthly index so the
        # CAGR/Calmar helpers (which annualise from the index span) behave.
        values.index = pd.date_range("2000-01-31", periods=len(values), freq="ME")
        calmar = calculate_calmar_ratio(values)
        max_dd = calculate_max_drawdown(values)
        annual = calculate_cagr(values)
        return sharpe, calmar, max_dd, annual

    def run_fast(self, strategy_returns: pd.Series) -> BootstrapResult:
        """Resample realised strategy returns directly (no backtest re-runs)."""
        r = strategy_returns.dropna().values
        t = len(r)
        if t < 12:
            raise ValueError(f"Need >= 12 return observations, got {t}")

        rng = np.random.default_rng(self.seed)
        idx = stationary_bootstrap_indices(t, self.expected_block, self.n_iter, rng)

        result = BootstrapResult(
            realized={},
            n_iter=self.n_iter,
            expected_block=self.expected_block,
            mode="fast",
        )
        r0_sharpe, r0_calmar, r0_dd, r0_annual = self._metrics_from_returns(
            r, self.periods_per_year
        )
        result.realized = {
            "sharpe": round(r0_sharpe, 4),
            "calmar": round(r0_calmar, 4),
            "max_drawdown": round(r0_dd, 4),
            "annual_return": round(r0_annual, 4),
        }
        for i in range(self.n_iter):
            s, c, dd, an = self._metrics_from_returns(r[idx[i]], self.periods_per_year)
            result.sharpe.append(s)
            result.calmar.append(c)
            result.max_drawdown.append(dd)
            result.annual_return.append(an)
        return result

    def run(
        self,
        strategy,
        prices: pd.DataFrame,
        engine,
        backtest_start,
        backtest_end,
        default_lookback_days: int = 252,
    ) -> BootstrapResult:
        """Faithful bootstrap: resample price returns, re-run the backtest each iter."""
        from backtesting.runner import run_single_backtest

        rets = prices.pct_change().dropna(how="all")
        t = len(rets)
        if t < 12:
            raise ValueError(f"Need >= 12 price observations, got {t}")
        rng = np.random.default_rng(self.seed)
        # Block length here is in trading-day periods of the price series.
        expected_block_days = max(1.0, self.block_months * 21)
        idx = stationary_bootstrap_indices(t, expected_block_days, self.n_iter, rng)

        base_row = prices.iloc[0]
        result = BootstrapResult(
            realized={},
            n_iter=self.n_iter,
            expected_block=expected_block_days,
            mode="rerun",
        )
        for i in range(self.n_iter):
            resampled = rets.iloc[idx[i]].reset_index(drop=True)
            synth = base_row.values * (1.0 + resampled).cumprod()
            synth.index = prices.index[: len(synth)]
            res = run_single_backtest(
                strategy,
                synth,
                synth.index[0],
                synth.index[-1],
                engine,
                default_lookback_days=default_lookback_days,
            )
            values = res.portfolio_history.get("total_value")
            if values is None or len(values) < 3:
                continue
            vr = values.pct_change().dropna()
            result.sharpe.append(
                calculate_sharpe_ratio(vr, periods_per_year=self.periods_per_year)
            )
            result.calmar.append(calculate_calmar_ratio(values))
            result.max_drawdown.append(calculate_max_drawdown(values))
            result.annual_return.append(calculate_cagr(values))
        return result
