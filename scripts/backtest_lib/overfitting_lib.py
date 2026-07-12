"""
Shared logic for ``scripts/run_all_overfitting.py`` — single-strategy /
reporting / IO helpers.

This module holds the pure analysis + IO + reporting helpers so the entry
script keeps only CLI parsing and orchestration. The batch-specific helpers
(n-trials estimation, DSR/k-fold batch, PBO sweeps, SPA) live in the sibling
``overfitting_batch_lib`` module.

Nothing here hard-codes a periods-per-year (252/12): the annualisation factor
is always inferred from the return-series spacing via
``analytics.metrics.infer_periods_per_year``.
"""

import json
import logging
import sys
from pathlib import Path
from typing import List, Optional

import pandas as pd

# Project root on path so the `analytics`/`backtesting`/`data`/… top-level
# packages resolve whether this module is imported as ``backtest_lib.*`` or
# directly.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from analytics.metrics import infer_periods_per_year  # noqa: E402
from analytics.overfitting import (  # noqa: E402
    OverfittingAnalysis,
    overfitting_analysis_to_dict,
)
from backtesting.results_schema import (  # noqa: E402
    OVERFITTING_FILE,
    STRATEGY_FILES,
    load_portfolio_values,
)
from backtesting.results_schema import strategy_dir as schema_strategy_dir  # noqa: E402
from data import HistoricalDataCache, align_dataframes  # noqa: E402
from strategies import (  # noqa: E402
    HRPStrategy,
    TrendFollowingStrategy,
    EqualWeightStrategy,
    MinimumVarianceStrategy,
    RiskParityStrategy,
    MomentumTopNStrategy,
)

logger = logging.getLogger(__name__)

RESULTS_DIR = Path("results/strategies")
CURRENCY = "GBP"
SYMBOLS = sorted(
    p.stem.upper()
    for p in (_PROJECT_ROOT / "strategy_definitions" / "assets").glob("*.json")
)

# Base strategy classes for Mode 1 parameter sweeps (single-strategy path)
STRATEGY_CLASSES = {
    "hrp": HRPStrategy,
    "trend_following": TrendFollowingStrategy,
    "equal_weight": EqualWeightStrategy,
    "minimum_variance": MinimumVarianceStrategy,
    "risk_parity": RiskParityStrategy,
    "momentum": MomentumTopNStrategy,
}


def parse_param(param_str: str) -> tuple:
    """Parse 'key=val1,val2,val3' into (key, [val1, val2, val3])."""
    key, values_str = param_str.split("=", 1)
    values = values_str.split(",")
    parsed = []
    for v in values:
        v = v.strip()
        try:
            parsed.append(int(v))
        except ValueError:
            try:
                parsed.append(float(v))
            except ValueError:
                parsed.append(v)
    return key, parsed


def load_cached_prices() -> pd.DataFrame:
    """Load close prices from local parquet cache."""
    cache = HistoricalDataCache(cache_dir="data/cache")
    data_dict = {}
    for symbol in SYMBOLS:
        df = cache.load_cached_data(
            symbol,
            pd.Timestamp("2015-01-01"),
            pd.Timestamp.now(),
            max_age_days=30,
        )
        if not df.empty:
            data_dict[symbol] = df
    if not data_dict:
        logger.error(
            "No cached data found. Run a backtest first:\n"
            "  python scripts/run_backtest.py --all"
        )
        sys.exit(1)
    return align_dataframes(data_dict)


def load_portfolio_history(strategy_key: str) -> Optional[pd.Series]:
    """Load portfolio total_value series; returns None if file missing."""
    path = (
        schema_strategy_dir(RESULTS_DIR.parent, strategy_key)
        / STRATEGY_FILES["portfolio_history"]
    )
    if not path.exists():
        return None
    return load_portfolio_values(RESULTS_DIR.parent, strategy_key)


def save_analysis(analysis: OverfittingAnalysis, strategy_key: str) -> Path:
    """Save overfitting_analysis.json to the strategy's results directory."""
    out_path = schema_strategy_dir(RESULTS_DIR.parent, strategy_key) / OVERFITTING_FILE
    out_path.parent.mkdir(parents=True, exist_ok=True)
    d = overfitting_analysis_to_dict(analysis)
    with open(out_path, "w") as f:
        json.dump(d, f, indent=2, default=str)
    return out_path


def print_analysis_report(analysis: OverfittingAnalysis) -> None:
    """Print a human-readable overfitting analysis report to stdout."""
    sep = "=" * 50
    print(f"\n{sep}")
    print(f"OVERFITTING ANALYSIS: {analysis.strategy_key}")
    print(sep)
    print(f"Parameter Combinations (N): {analysis.n_param_combinations}")

    if analysis.dsr is not None:
        d = analysis.dsr
        print(f"Return Periods (T):        {d.t_periods}")
        print()
        print("--- Deflated Sharpe Ratio ---")
        print(f"Observed SR (annualised):  {d.observed_sharpe:.4f}")
        print(f"Reference SR₀:             {d.sharpe_reference:.4f}")
        skew_str = f"{d.skewness:.3f}"
        kurt_str = f"{d.excess_kurtosis:.3f}"
        print(f"Skewness / Excess Kurt:    {skew_str} / {kurt_str}")

        verdict_icon = (
            "✓" if d.verdict == "PASS" else ("⚠" if d.verdict == "WARN" else "✗")
        )
        threshold_str = (
            f">= {d.threshold_pass}"
            if d.verdict == "PASS"
            else (
                f">= {d.threshold_warn}"
                if d.verdict == "WARN"
                else f"< {d.threshold_warn}"
            )
        )
        print(f"DSR: {d.dsr:.4f}  {verdict_icon} {d.verdict} ({threshold_str})")
    else:
        print("\n--- Deflated Sharpe Ratio: SKIPPED ---")

    if analysis.pbo is not None:
        p = analysis.pbo
        print()
        print("--- Probability of Backtest Overfitting ---")
        print(f"CSCV Partitions:           {p.n_combinations:,}")
        print(f"S subsets:                 {p.s_subsets}")
        print(f"Prob OOS Loss:             {p.prob_oos_loss:.1%}")

        verdict_icon = (
            "✓" if p.verdict == "PASS" else ("⚠" if p.verdict == "WARN" else "✗")
        )
        threshold_str = (
            f"<= {p.threshold_pass}"
            if p.verdict == "PASS"
            else (
                f"<= {p.threshold_warn}"
                if p.verdict == "WARN"
                else f"> {p.threshold_warn}"
            )
        )
        print(f"PBO: {p.pbo:.4f}  {verdict_icon} {p.verdict} ({threshold_str})")
    elif analysis.n_param_combinations < 2:
        print("\n--- PBO: SKIPPED (N < 2) ---")
    else:
        print("\n--- PBO: SKIPPED (no return matrix) ---")

    if analysis.kfold is not None:
        k = analysis.kfold
        print()
        print("--- K-Fold Temporal Stability ---")
        print(f"Folds (k):                 {k.n_folds}")
        print(
            f"Fold Sharpes:              [{', '.join(f'{s:.2f}' for s in k.fold_sharpes)}]"
        )
        print(f"Mean / Std:                {k.mean_sharpe:.4f} / {k.std_sharpe:.4f}")
        print(f"Worst Fold Sharpe:         {k.worst_fold_sharpe:.4f}")
        if k.embargo_periods > 0:
            print(f"Embargo Periods:           {k.embargo_periods}")

        verdict_icon = (
            "✓" if k.verdict == "PASS" else ("⚠" if k.verdict == "WARN" else "✗")
        )
        threshold_str = (
            f">= {k.threshold_pass}"
            if k.verdict == "PASS"
            else (
                f">= {k.threshold_warn}"
                if k.verdict == "WARN"
                else f"< {k.threshold_warn}"
            )
        )
        print(
            f"Frac Positive: {k.fraction_positive:.1%}  "
            f"{verdict_icon} {k.verdict} ({threshold_str})"
        )
    else:
        print("\n--- K-Fold Stability: SKIPPED ---")

    # Overall verdict
    verdicts = []
    if analysis.dsr:
        verdicts.append(analysis.dsr.verdict)
    if analysis.pbo:
        verdicts.append(analysis.pbo.verdict)
    if analysis.kfold:
        verdicts.append(analysis.kfold.verdict)

    if verdicts:
        if all(v == "PASS" for v in verdicts):
            overall = "PASS"
        elif any(v == "FAIL" for v in verdicts):
            overall = "FAIL"
        else:
            overall = "WARN"
        icon = "✓" if overall == "PASS" else ("⚠" if overall == "WARN" else "✗")
        print()
        print(f"Overall: {icon} {overall}")

    if analysis.errors:
        print()
        print("Errors:")
        for e in analysis.errors:
            print(f"  ✗ {e}")

    print(sep + "\n")


def print_summary_table(rows: List[dict]) -> None:
    """Print aligned summary table to stdout."""
    if not rows:
        return

    headers = list(rows[0].keys())
    col_widths = {h: max(len(h), max(len(str(r[h])) for r in rows)) for h in headers}
    header_line = "  ".join(h.ljust(col_widths[h]) for h in headers)
    sep = "  ".join("-" * col_widths[h] for h in headers)

    print()
    print(header_line)
    print(sep)
    for row in rows:
        line = "  ".join(str(row[h]).ljust(col_widths[h]) for h in headers)
        print(line)
    print()


def print_verdict_counts(rows: List[dict], col: str) -> None:
    from collections import Counter

    counts = Counter(r[col] for r in rows)
    total = len(rows)
    parts = []
    for v in ("PASS", "WARN", "FAIL", "N/A"):
        if counts[v]:
            parts.append(f"{v}: {counts[v]}/{total}")
    print(f"  {col}: " + "  |  ".join(parts))


def run_cpcv_analysis(strategy_key: str, n_groups: int, embargo_days: int) -> None:
    """Run CPCV from saved portfolio history and merge into overfitting_analysis.json."""
    import json as _json

    from analytics.cpcv import CPCVEngine

    total_values = load_portfolio_history(strategy_key)
    returns = total_values.pct_change().dropna()
    ppy = infer_periods_per_year(total_values.index)
    result = CPCVEngine(
        n_groups=n_groups,
        n_test_groups=2,
        embargo_days=embargo_days,
        periods_per_year=ppy,
    ).run(returns)

    out_dir = schema_strategy_dir(RESULTS_DIR.parent, strategy_key)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / OVERFITTING_FILE
    if path.exists():
        with open(path) as f:
            payload = _json.load(f)
    else:
        payload = {"strategy_key": strategy_key}
    payload["cpcv"] = result.to_dict()
    with open(path, "w") as f:
        _json.dump(payload, f, indent=2)

    print(f"\nCPCV — {strategy_key}")
    print(f"  Combinations : {result.n_combinations}")
    print(f"  Mean OOS Sharpe   : {result.mean_sharpe:.3f}")
    print(f"  5th pct OOS Sharpe: {result.pct5_sharpe:.3f}")
    print(f"  P(Sharpe>0)  : {result.prob_oos_sharpe_positive:.2%}")
    print(f"  Verdict      : {result.verdict}")
    print(f"  Saved to     : {path}\n")


def run_bootstrap_analysis(
    strategy_key: str, n_iter: int, block_months: int, fast: bool
) -> None:
    """Run block bootstrap from saved portfolio history; merge into JSON."""
    import json as _json

    from analytics.bootstrap import BlockBootstrap

    if not fast:
        print(
            "  (full re-run bootstrap needs live prices/engine; from saved "
            "results only --bootstrap-fast is available — using fast mode.)"
        )
    total_values = load_portfolio_history(strategy_key)
    returns = total_values.pct_change().dropna()
    ppy = infer_periods_per_year(total_values.index)
    result = BlockBootstrap(
        n_iter=n_iter, block_months=block_months, periods_per_year=ppy, seed=0
    ).run_fast(returns)

    out_dir = schema_strategy_dir(RESULTS_DIR.parent, strategy_key)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / OVERFITTING_FILE
    payload = (
        _json.load(open(path)) if path.exists() else {"strategy_key": strategy_key}
    )
    payload["bootstrap"] = result.to_dict()
    with open(path, "w") as f:
        _json.dump(payload, f, indent=2)

    sh = result.to_dict()["sharpe"]
    print(f"\nBLOCK BOOTSTRAP — {strategy_key}")
    print(f"  Iterations       : {result.n_iter}")
    print(f"  Realized Sharpe  : {result.realized.get('sharpe')}")
    print(f"  Bootstrap mean   : {sh['mean']}  (5th pct {sh['pct5']})")
    print(f"  Saved to         : {path}\n")
