"""
One-shot validation battery for a saved strategy.

Composes four existing overfitting-detection tools — MinBTL, DSR, CPCV, and
the block bootstrap (Phases 6-9) — into a single pass/warn/fail verdict per
strategy. This module is a thin composition layer: it reuses
``analytics.overfitting.calculate_deflated_sharpe_ratio`` /
``calculate_minbtl``, ``analytics.cpcv.CPCVEngine``, and
``analytics.bootstrap.BlockBootstrap`` directly rather than reimplementing
any statistical logic. See ``scripts/validate_strategy.py`` for the CLI.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from analytics.bootstrap import BlockBootstrap
from analytics.cpcv import CPCVEngine
from analytics.metrics import calculate_sharpe_ratio
from analytics.overfitting import calculate_deflated_sharpe_ratio, calculate_minbtl
from backtesting.results_schema import (
    STRATEGY_FILES,
    load_portfolio_values,
    strategy_dir,
)

logger = logging.getLogger(__name__)

PERIODS_PER_YEAR = 12


def _json_safe(obj: Any) -> Any:
    """Recursively map non-finite floats (inf/-inf/NaN) to None.

    Keeps ``json.dumps`` output valid — it would otherwise emit the
    non-standard ``Infinity``/``NaN`` tokens that strict parsers (and the
    dashboard's ``JSON.parse``) reject.
    """
    if isinstance(obj, float):
        return round(obj, 6) if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


@dataclass
class TestOutcome:
    """Result of a single test within the validation battery."""

    name: str
    verdict: str  # PASS / WARN / FAIL / SKIP
    values: Dict[str, Any] = field(default_factory=dict)
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "verdict": self.verdict,
            "values": _json_safe(self.values),
            "note": self.note,
        }


@dataclass
class ValidationResult:
    """Combined output of ``run_validation_battery``."""

    strategy_key: str
    generated: str
    tests: List[TestOutcome]
    overall: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_key": self.strategy_key,
            "generated": self.generated,
            "tests": [t.to_dict() for t in self.tests],
            "overall": self.overall,
        }


def _overall_verdict(tests: List[TestOutcome]) -> str:
    """FAIL if MinBTL/DSR/CPCV FAIL; else WARN if any test WARN/SKIP; else PASS.

    Bootstrap (fast mode) never contributes a FAIL by construction — its
    worst outcome is WARN — so it only ever pulls the overall verdict down
    to WARN, never to FAIL.
    """
    by_name = {t.name: t.verdict for t in tests}
    if any(by_name.get(n) == "FAIL" for n in ("minbtl", "dsr", "cpcv")):
        return "FAIL"
    if any(t.verdict in ("WARN", "SKIP") for t in tests):
        return "WARN"
    return "PASS"


def run_validation_battery(
    strategy_key: str,
    results_dir: str | Path,
    *,
    n_trials: int,
    cpcv_folds: int = 6,
    bootstrap_n: int = 500,
    block_months: int = 3,
    embargo_days: int = 10,
) -> ValidationResult:
    """
    Run MinBTL -> DSR -> CPCV -> block bootstrap for a saved strategy.

    ``strategy_key``/``results_dir``: identify ``<results_dir>/strategies/
    <strategy_key>/portfolio_history.json``, loaded via
    ``backtesting.results_schema.load_portfolio_values`` (monthly total-value
    series -> ``pct_change().dropna()`` returns, matching
    ``scripts/run_overfitting.py`` Mode 2). Raises ``FileNotFoundError`` if
    the strategy has no saved results.

    ``n_trials``: number of configurations this strategy was effectively
    selected from (see ``scripts/run_all_overfitting.py:build_n_trials_map``);
    used for both DSR and MinBTL, floored at 2 (both require N >= 2).
    ``cpcv_folds``/``embargo_days``: passed to ``CPCVEngine``.
    ``bootstrap_n``/``block_months``: passed to ``BlockBootstrap.run_fast``.

    Any test that cannot run on the available history (too few observations)
    is marked SKIP with an explanatory note instead of raising, EXCEPT
    MinBTL, which always produces a verdict (it falls back to
    ``analytics.metrics.calculate_sharpe_ratio`` for the observed Sharpe if
    DSR itself failed to compute).

    Returns
    -------
    ValidationResult
    """
    portfolio_path = (
        strategy_dir(results_dir, strategy_key) / STRATEGY_FILES["portfolio_history"]
    )
    if not portfolio_path.exists():
        raise FileNotFoundError(
            f"No saved results for strategy '{strategy_key}' "
            f"({portfolio_path} not found) — run a backtest first."
        )

    if n_trials < 2:
        logger.warning("n_trials=%d < 2; flooring to 2 for DSR/MinBTL.", n_trials)
        n_trials = 2

    total_values = load_portfolio_values(results_dir, strategy_key)
    returns = total_values.pct_change().dropna()

    tests: List[TestOutcome] = []

    # --- DSR (computed first so MinBTL can reuse its observed_sharpe) ---
    dsr_result = None
    try:
        dsr_result = calculate_deflated_sharpe_ratio(
            returns=returns,
            n_trials=n_trials,
            periods_per_year=PERIODS_PER_YEAR,
        )
        tests.append(
            TestOutcome(
                name="dsr",
                verdict=dsr_result.verdict,
                values={
                    "dsr": dsr_result.dsr,
                    "observed_sharpe": dsr_result.observed_sharpe,
                    "sharpe_reference": dsr_result.sharpe_reference,
                    "n_trials": dsr_result.n_trials,
                    "t_periods": dsr_result.t_periods,
                },
            )
        )
    except Exception as exc:
        logger.warning("DSR could not be computed for %s: %s", strategy_key, exc)
        tests.append(
            TestOutcome(name="dsr", verdict="SKIP", note=f"DSR could not run: {exc}")
        )

    # --- MinBTL (always runs, even if DSR above failed) ---
    if dsr_result is not None:
        observed_sharpe = dsr_result.observed_sharpe
    else:
        observed_sharpe = calculate_sharpe_ratio(
            returns, periods_per_year=PERIODS_PER_YEAR
        )
    actual_years = len(returns) / PERIODS_PER_YEAR
    minbtl_result = calculate_minbtl(
        observed_sharpe_annualized=observed_sharpe,
        n_trials=n_trials,
        actual_years=actual_years,
    )
    tests.append(
        TestOutcome(
            name="minbtl",
            verdict=minbtl_result.verdict,
            values={
                "min_years": minbtl_result.min_years,
                "actual_years": minbtl_result.actual_years,
                "n_trials": minbtl_result.n_trials,
                "observed_sharpe": minbtl_result.observed_sharpe,
            },
        )
    )

    # --- CPCV ---
    try:
        cpcv_result = CPCVEngine(
            n_groups=cpcv_folds,
            n_test_groups=2,
            embargo_days=embargo_days,
            periods_per_year=PERIODS_PER_YEAR,
        ).run(returns)
        tests.append(
            TestOutcome(
                name="cpcv",
                verdict=cpcv_result.verdict,
                values={
                    "mean_sharpe": cpcv_result.mean_sharpe,
                    "pct5_sharpe": cpcv_result.pct5_sharpe,
                    "prob_oos_sharpe_positive": cpcv_result.prob_oos_sharpe_positive,
                    "n_combinations": cpcv_result.n_combinations,
                },
            )
        )
    except Exception as exc:
        logger.warning("CPCV could not run for %s: %s", strategy_key, exc)
        tests.append(
            TestOutcome(name="cpcv", verdict="SKIP", note=f"CPCV could not run: {exc}")
        )

    # --- Block bootstrap (fast mode: resamples realised returns only) ---
    try:
        bootstrap_result = BlockBootstrap(
            n_iter=bootstrap_n,
            block_months=block_months,
            periods_per_year=PERIODS_PER_YEAR,
        ).run_fast(returns)
        sharpe_summary = bootstrap_result.to_dict()["sharpe"]
        pct5 = sharpe_summary["pct5"]
        # Never FAIL from bootstrap (fast mode only) — worst case is WARN.
        verdict = "WARN" if (pct5 is not None and pct5 < 0) else "PASS"
        tests.append(
            TestOutcome(
                name="bootstrap",
                verdict=verdict,
                values={
                    "realized_sharpe": bootstrap_result.realized.get("sharpe"),
                    "sharpe_mean": sharpe_summary["mean"],
                    "sharpe_pct5": pct5,
                },
                note="fast mode: resamples realised returns, no backtest re-runs",
            )
        )
    except Exception as exc:
        logger.warning("Bootstrap could not run for %s: %s", strategy_key, exc)
        tests.append(
            TestOutcome(
                name="bootstrap",
                verdict="SKIP",
                note=f"Bootstrap could not run: {exc}",
            )
        )

    overall = _overall_verdict(tests)
    return ValidationResult(
        strategy_key=strategy_key,
        generated=datetime.now(timezone.utc).date().isoformat(),
        tests=tests,
        overall=overall,
    )
