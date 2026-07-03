"""
Stress testing framework for portfolio backtests.

Analyses strategy performance during historical crisis periods and supports
leave-one-crisis-out (scenario removal) analysis to identify how much of a
strategy's return depends on any single event.

Crisis periods defined:
- 2008 GFC: Oct 2007 – Mar 2009
- 2011 EU Debt Crisis: Jul – Oct 2011
- 2015-16 EM/China Rout: Aug 2015 – Feb 2016
- 2020 COVID Crash: Feb – Mar 2020
- 2022 Rate Spike: Jan – Oct 2022

Scenario removal supports two modes:
- ``excise`` (default): re-slice the already-computed portfolio value series
  with each crisis window removed and recompute Sharpe/Calmar. Cheap; needs no
  extra inputs. This is what the ``--stress-test`` path uses.
- ``rerun``: a true leave-one-crisis-out — drop each crisis window from the
  price data and RE-RUN the backtest, then compare full vs LOO Sharpe/Calmar.
  Requires the strategy, prices, and engine.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

import pandas as pd

from analytics.metrics import (
    calculate_cagr,
    calculate_calmar_ratio,
    calculate_max_drawdown,
    calculate_sharpe_ratio,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Crisis period definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CrisisPeriod:
    name: str
    start: date
    end: date
    description: str


CRISIS_PERIODS: List[CrisisPeriod] = [
    CrisisPeriod(
        name="2008 GFC",
        start=date(2007, 10, 1),
        end=date(2009, 3, 31),
        description="Global Financial Crisis — peak-to-trough equity drawdown",
    ),
    CrisisPeriod(
        name="2011 EU Debt",
        start=date(2011, 7, 1),
        end=date(2011, 10, 31),
        description="European Sovereign Debt Crisis — Italy/Spain contagion",
    ),
    CrisisPeriod(
        name="2015-16 EM Rout",
        start=date(2015, 8, 1),
        end=date(2016, 2, 29),
        description="China slowdown / EM capital outflows / oil collapse",
    ),
    CrisisPeriod(
        name="2020 COVID",
        start=date(2020, 2, 19),
        end=date(2020, 3, 31),
        description="COVID-19 pandemic — fastest 30% drawdown in S&P history",
    ),
    CrisisPeriod(
        name="2022 Rate Spike",
        start=date(2022, 1, 1),
        end=date(2022, 10, 31),
        description="Central bank rate hiking cycle — global bond/equity selloff",
    ),
]


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class CrisisMetrics:
    """Performance metrics for a single crisis window."""

    crisis: CrisisPeriod
    total_return: float  # decimal, e.g. -0.15 = -15%
    annualised_return: float  # CAGR over the window
    max_drawdown: float  # negative decimal
    recovery_days: int  # calendar days from trough to recovery (0 if not recovered)
    sharpe: float
    has_data: bool  # False if strategy had no data in this window


@dataclass
class ScenarioRemovalResult:
    """Result of a leave-one-crisis-out run.

    ``sharpe_delta``/``calmar_delta`` are full minus leave-one-out; a positive
    delta means the crisis window *raised* the metric (i.e. the strategy's
    headline number depends on that event).
    """

    crisis: CrisisPeriod
    full_sharpe: float  # Sharpe using all history
    loo_sharpe: float  # Sharpe with this crisis window excluded
    sharpe_delta: float  # full_sharpe - loo_sharpe
    full_calmar: float = 0.0  # Calmar using all history
    loo_calmar: float = 0.0  # Calmar with this crisis window excluded
    calmar_delta: float = 0.0  # full_calmar - loo_calmar


def _safe_round(x: float, ndigits: int) -> Optional[float]:
    """Round, mapping non-finite values (inf/-inf/NaN) to None.

    Keeps serialized JSON valid — ``json.dumps`` would otherwise emit the
    non-standard ``Infinity``/``NaN`` tokens that break strict parsers (and the
    dashboard's ``JSON.parse``).
    """
    if x is None or not math.isfinite(x):
        return None
    return round(x, ndigits)


@dataclass
class StressTestReport:
    """Aggregated stress test output for a strategy."""

    strategy_name: str
    crisis_metrics: List[CrisisMetrics]
    scenario_removal: List[ScenarioRemovalResult]
    scenario_removal_mode: str = "excise"

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "scenario_removal_mode": self.scenario_removal_mode,
            "crisis_metrics": [
                {
                    "crisis_name": m.crisis.name,
                    "crisis_description": m.crisis.description,
                    "start": m.crisis.start.isoformat(),
                    "end": m.crisis.end.isoformat(),
                    "total_return_pct": round(m.total_return * 100, 2),
                    "annualised_return_pct": round(m.annualised_return * 100, 2),
                    "max_drawdown_pct": round(m.max_drawdown * 100, 2),
                    "recovery_days": m.recovery_days,
                    "sharpe": round(m.sharpe, 3),
                    "has_data": m.has_data,
                }
                for m in self.crisis_metrics
            ],
            "scenario_removal": [
                {
                    "crisis_name": r.crisis.name,
                    "full_sharpe": _safe_round(r.full_sharpe, 3),
                    "loo_sharpe": _safe_round(r.loo_sharpe, 3),
                    "sharpe_delta": _safe_round(r.sharpe_delta, 3),
                    "full_calmar": _safe_round(r.full_calmar, 3),
                    "loo_calmar": _safe_round(r.loo_calmar, 3),
                    "calmar_delta": _safe_round(r.calmar_delta, 3),
                }
                for r in self.scenario_removal
            ],
        }


# ---------------------------------------------------------------------------
# Core analyser
# ---------------------------------------------------------------------------


class StressTester:
    """
    Analyses strategy performance during historical crisis periods.

    Works directly with a portfolio value Series (DatetimeIndex, daily values)
    extracted from BacktestResults.portfolio_history['total_value'].

    Example:
        tester = StressTester(values, strategy_name="HRP Ward")
        report = tester.run()
        print(report.to_dict())
    """

    # Minimum surviving observations required to compute stable LOO metrics.
    MIN_LOO_OBSERVATIONS = 60

    def __init__(
        self,
        values: pd.Series,
        strategy_name: str,
        crises: Optional[List[CrisisPeriod]] = None,
    ) -> None:
        """
        Args:
            values: Portfolio value Series with DatetimeIndex (daily).
            strategy_name: Human-readable name used in the report.
            crises: Crisis periods to analyse. Defaults to CRISIS_PERIODS.
        """
        if not isinstance(values.index, pd.DatetimeIndex):
            raise ValueError("values must have a DatetimeIndex")
        self.values = values.sort_index()
        self.strategy_name = strategy_name
        self.crises = crises if crises is not None else CRISIS_PERIODS

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> StressTestReport:
        """Run all crisis-period analyses (excise-mode scenario removal)."""
        crisis_metrics = [self._analyse_crisis(c) for c in self.crises]
        scenario_removal = self.run_leave_one_out(mode="excise")
        return StressTestReport(
            strategy_name=self.strategy_name,
            crisis_metrics=crisis_metrics,
            scenario_removal=scenario_removal,
            scenario_removal_mode="excise",
        )

    # ------------------------------------------------------------------
    # Crisis window metrics
    # ------------------------------------------------------------------

    def _analyse_crisis(self, crisis: CrisisPeriod) -> CrisisMetrics:
        """Compute metrics for the strategy during a single crisis window."""
        window = self._slice(crisis)

        if window is None or len(window) < 5:
            logger.debug("No data for crisis %s", crisis.name)
            return CrisisMetrics(
                crisis=crisis,
                total_return=0.0,
                annualised_return=0.0,
                max_drawdown=0.0,
                recovery_days=0,
                sharpe=0.0,
                has_data=False,
            )

        returns = window.pct_change().dropna()
        total_return = window.iloc[-1] / window.iloc[0] - 1
        annualised = calculate_cagr(window)
        max_dd = calculate_max_drawdown(window)
        sharpe = calculate_sharpe_ratio(returns)
        recovery = self._recovery_days(window, crisis)

        return CrisisMetrics(
            crisis=crisis,
            total_return=total_return,
            annualised_return=annualised,
            max_drawdown=max_dd,
            recovery_days=recovery,
            sharpe=sharpe,
            has_data=True,
        )

    def _recovery_days(self, window: pd.Series, crisis: CrisisPeriod) -> int:
        """
        Days from the trough of the crisis window to recovery of the
        pre-crisis peak. Searches beyond the crisis end date in the full
        series. Returns 0 if already at or above peak at end of window,
        and -1 if not yet recovered as of the last data point.
        """
        pre_crisis_peak = self.values.loc[: window.index[0]].iloc[-1]
        trough_idx = window.idxmin()

        # Look for recovery in the tail of the full series after the trough
        tail = self.values.loc[trough_idx:]
        recovered = tail[tail >= pre_crisis_peak]

        if recovered.empty:
            return -1  # not yet recovered

        return (recovered.index[0] - trough_idx).days

    # ------------------------------------------------------------------
    # Leave-one-crisis-out
    # ------------------------------------------------------------------

    def run_leave_one_out(
        self,
        mode: str = "excise",
        *,
        strategy=None,
        prices: Optional[pd.DataFrame] = None,
        engine=None,
        backtest_start=None,
        backtest_end=None,
        default_lookback_days: int = 252,
    ) -> List[ScenarioRemovalResult]:
        """
        Leave-one-crisis-out scenario removal.

        Args:
            mode: ``"excise"`` (default) re-slices the existing value series
                with each crisis removed; ``"rerun"`` drops the crisis window
                from ``prices`` and re-runs the backtest for a true LOO.
            strategy, prices, engine, backtest_start, backtest_end:
                required for ``mode="rerun"`` (ValueError otherwise).
            default_lookback_days: fallback lookback passed to the runner.

        Returns:
            List[ScenarioRemovalResult], one per crisis with enough surviving
            data (crises leaving too little data are skipped).
        """
        if mode == "excise":
            return self._run_leave_one_out_excise()
        if mode == "rerun":
            return self._run_leave_one_out_rerun(
                strategy=strategy,
                prices=prices,
                engine=engine,
                backtest_start=backtest_start,
                backtest_end=backtest_end,
                default_lookback_days=default_lookback_days,
            )
        raise ValueError(f"Unknown scenario-removal mode: {mode!r}")

    def _run_leave_one_out_excise(self) -> List[ScenarioRemovalResult]:
        """Excise mode: re-slice the value series with each crisis removed."""
        full_returns = self.values.pct_change().dropna()
        full_sharpe = calculate_sharpe_ratio(full_returns)
        full_calmar = calculate_calmar_ratio(self.values)

        results: List[ScenarioRemovalResult] = []
        for crisis in self.crises:
            loo_values = self._exclude(crisis)
            if loo_values is None or len(loo_values) < self.MIN_LOO_OBSERVATIONS:
                logger.debug("Insufficient data after excluding %s", crisis.name)
                continue
            loo_returns = loo_values.pct_change().dropna()
            loo_sharpe = calculate_sharpe_ratio(loo_returns)
            loo_calmar = calculate_calmar_ratio(loo_values)
            results.append(
                ScenarioRemovalResult(
                    crisis=crisis,
                    full_sharpe=full_sharpe,
                    loo_sharpe=loo_sharpe,
                    sharpe_delta=full_sharpe - loo_sharpe,
                    full_calmar=full_calmar,
                    loo_calmar=loo_calmar,
                    calmar_delta=full_calmar - loo_calmar,
                )
            )
        return results

    def _run_leave_one_out_rerun(
        self,
        *,
        strategy,
        prices: Optional[pd.DataFrame],
        engine,
        backtest_start,
        backtest_end,
        default_lookback_days: int,
    ) -> List[ScenarioRemovalResult]:
        """Rerun mode: drop each crisis window from prices and re-run the backtest."""
        missing = [
            name
            for name, val in (
                ("strategy", strategy),
                ("prices", prices),
                ("engine", engine),
                ("backtest_start", backtest_start),
                ("backtest_end", backtest_end),
            )
            if val is None
        ]
        if missing:
            raise ValueError(
                "run_leave_one_out(mode='rerun') requires: " + ", ".join(missing)
            )

        # Lazy import keeps analytics import-safe even if backtesting grows an
        # analytics dependency later.
        from backtesting.runner import run_single_backtest

        full_returns = self.values.pct_change().dropna()
        full_sharpe = calculate_sharpe_ratio(full_returns)
        full_calmar = calculate_calmar_ratio(self.values)

        results: List[ScenarioRemovalResult] = []
        for crisis in self.crises:
            start = pd.Timestamp(crisis.start)
            end = pd.Timestamp(crisis.end)
            reduced = prices.loc[(prices.index < start) | (prices.index > end)]
            if len(reduced) < self.MIN_LOO_OBSERVATIONS:
                logger.debug(
                    "Insufficient price data after excluding %s (rerun)", crisis.name
                )
                continue

            loo_results = run_single_backtest(
                strategy,
                reduced,
                backtest_start,
                backtest_end,
                engine,
                default_lookback_days=default_lookback_days,
            )
            loo_values = loo_results.portfolio_history.get("total_value")
            if loo_values is None or len(loo_values) < self.MIN_LOO_OBSERVATIONS:
                logger.debug("Rerun for %s produced too little data", crisis.name)
                continue

            loo_returns = loo_values.pct_change().dropna()
            loo_sharpe = calculate_sharpe_ratio(loo_returns)
            loo_calmar = calculate_calmar_ratio(loo_values)
            results.append(
                ScenarioRemovalResult(
                    crisis=crisis,
                    full_sharpe=full_sharpe,
                    loo_sharpe=loo_sharpe,
                    sharpe_delta=full_sharpe - loo_sharpe,
                    full_calmar=full_calmar,
                    loo_calmar=loo_calmar,
                    calmar_delta=full_calmar - loo_calmar,
                )
            )
        return results

    def _run_leave_one_out(self) -> List[ScenarioRemovalResult]:
        """Backward-compatible alias for excise-mode scenario removal."""
        return self.run_leave_one_out(mode="excise")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _slice(self, crisis: CrisisPeriod) -> Optional[pd.Series]:
        """Return the values Series sliced to the crisis window."""
        start = pd.Timestamp(crisis.start)
        end = pd.Timestamp(crisis.end)
        sliced = self.values.loc[start:end]
        return sliced if not sliced.empty else None

    def _exclude(self, crisis: CrisisPeriod) -> Optional[pd.Series]:
        """Return the values Series with the crisis window removed."""
        start = pd.Timestamp(crisis.start)
        end = pd.Timestamp(crisis.end)
        excluded = self.values.loc[
            (self.values.index < start) | (self.values.index > end)
        ]
        return excluded if not excluded.empty else None


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def run_stress_test(
    values: pd.Series,
    strategy_name: str,
    crises: Optional[List[CrisisPeriod]] = None,
) -> StressTestReport:
    """
    Convenience wrapper: create a StressTester and return the full report.

    Args:
        values: Daily portfolio value Series with DatetimeIndex.
        strategy_name: Name used in report output.
        crises: Optional override of crisis periods (defaults to CRISIS_PERIODS).

    Returns:
        StressTestReport with crisis metrics and scenario removal results.
    """
    return StressTester(values, strategy_name, crises).run()
