"""
Overfitting analysis (DSR + k-fold + PBO) for strategies.

TWO MODES:

  BATCH MODE (default): DSR + k-fold for all strategies in results/strategies/
    python scripts/run_all_overfitting.py                       # all strategies, DSR + k-fold
    python scripts/run_all_overfitting.py --skip-pbo           # fast: DSR + k-fold only
    python scripts/run_all_overfitting.py --n-folds 5          # custom fold count
    python scripts/run_all_overfitting.py --embargo-days 30    # purged/embargoed k-fold

  SINGLE STRATEGY MODE:
    # Mode 1: parameter sweep → DSR + PBO + k-fold
    python scripts/run_all_overfitting.py \\
        --strategy hrp \\
        --param linkage_method=single,complete,ward

    python scripts/run_all_overfitting.py \\
        --strategy trend_following \\
        --param lookback_days=126,252,504 \\
        --param half_life_days=30,60,90

    # Mode 2: DSR + k-fold from existing backtest results
    python scripts/run_all_overfitting.py --strategy hrp_ward --n-trials 3
"""

import argparse
import json
import logging
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from analytics.composed_pbo import run_composed_pbo_groups
from analytics.metrics import infer_periods_per_year  # noqa: E402
from analytics.overfitting import (
    OverfittingAnalysis,
    calculate_deflated_sharpe_ratio,
    calculate_minbtl,
    run_overfitting_analysis,
    overfitting_analysis_to_dict,
)
from analytics.overfitting_results import build_walk_forward_result
from backtesting.results_schema import (
    OVERFITTING_FILE,
    STRATEGY_FILES,
    load_portfolio_values,
)
from backtesting.results_schema import strategy_dir as schema_strategy_dir
from data import HistoricalDataCache, align_dataframes
from optimization import ParameterSweep, WalkForwardAnalysis
from strategies import (
    AssetStrategy,
    HRPStrategy,
    TrendFollowingStrategy,
    EqualWeightStrategy,
    MinimumVarianceStrategy,
    RiskParityStrategy,
    MomentumTopNStrategy,
)
from strategies.strategy_loader import StrategyLoader

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

RESULTS_DIR = Path("results/strategies")
CURRENCY = "GBP"
SYMBOLS = sorted(
    p.stem.upper()
    for p in (Path(__file__).parent.parent / "strategy_definitions" / "assets").glob(
        "*.json"
    )
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


# Parameter grids for PBO sweeps per base strategy family
PBO_PARAM_GRIDS: Dict[str, dict] = {
    "hrp": {
        "strategy_class": HRPStrategy,
        "param_grid": {"linkage_method": ["single", "complete", "average", "ward"]},
    },
    "trend_following": {
        "strategy_class": TrendFollowingStrategy,
        "param_grid": {
            "lookback_days": [126, 252, 504],
            "half_life_days": [30, 60, 90],
        },
    },
    "momentum": {
        "strategy_class": MomentumTopNStrategy,
        "param_grid": {"top_n": [1, 2, 3], "lookback_days": [126, 252]},
    },
    "minimum_variance": {
        "strategy_class": MinimumVarianceStrategy,
        "param_grid": {"lookback_days": [126, 252, 504]},
    },
    "risk_parity": {
        "strategy_class": RiskParityStrategy,
        "param_grid": {"lookback_days": [126, 252, 504]},
    },
    "equal_weight": {
        "strategy_class": EqualWeightStrategy,
        "param_grid": {"rebalance_threshold": [0.0, 0.02, 0.05]},
    },
}


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


def _load_class_lookup(strategy_keys: List[str]) -> Dict[str, str]:
    """
    Map each strategy_key -> its definition's ``class`` field, via
    ``StrategyLoader``. Keys whose definition can't be loaded map to
    themselves (forming a singleton class), so they don't crash the batch
    or get incorrectly grouped with an unrelated family.
    """
    loader = StrategyLoader()
    lookup: Dict[str, str] = {}
    for key in strategy_keys:
        try:
            definition = loader.load_definition(key)
            lookup[key] = definition.get("class") or key
        except Exception as exc:
            logger.warning(
                "Could not load definition for %s (%s); treating as its own class.",
                key,
                exc,
            )
            lookup[key] = key
    return lookup


def build_n_trials_map(
    strategy_keys: List[str],
    class_lookup: Optional[Dict[str, str]] = None,
) -> Dict[str, int]:
    """
    Estimate n_trials (N) for DSR / MinBTL per strategy key.

    Two-tier logic (fixes the old bug of lumping trend_following,
    trend_signal_rp, trend_signal_mvo together just because they share a
    "trend" prefix token — they are different strategy classes):

    (a) If a strategy's key matches a ``PBO_PARAM_GRIDS`` family (by prefix)
        AND its definition ``class`` equals that family's
        ``strategy_class``, n_trials = the cartesian product size of that
        family's grid — the TRUE number of configurations swept.
    (b) Otherwise, group by the definition's ``class`` field and count real
        siblings sharing that class.

    Floors n_trials at 2 (DSR/MinBTL require N >= 2).

    Parameters
    ----------
    class_lookup : dict, optional
        strategy_key -> definition class name. If None (production
        default), loaded via ``_load_class_lookup``. Tests pass a
        synthetic dict directly to avoid touching the filesystem.
    """
    if class_lookup is None:
        class_lookup = _load_class_lookup(strategy_keys)

    n_trials_map: Dict[str, int] = {}
    remaining: List[str] = []

    for key in strategy_keys:
        family = None
        for fam, cfg in PBO_PARAM_GRIDS.items():
            if key != fam and not key.startswith(fam + "_"):
                continue
            if class_lookup.get(key) == cfg["strategy_class"].__name__:
                family = fam
                break
        if family is not None:
            grid = PBO_PARAM_GRIDS[family]["param_grid"]
            n = 1
            for values in grid.values():
                n *= len(values)
            n_trials_map[key] = max(n, 2)
        else:
            remaining.append(key)

    class_counts = Counter(class_lookup.get(k, k) for k in remaining)
    for key in remaining:
        n_trials_map[key] = max(class_counts[class_lookup.get(key, key)], 2)

    return n_trials_map


def run_dsr_kfold_batch(
    strategy_keys: List[str],
    n_folds: int,
    n_trials_map: Dict[str, int],
    embargo_days: int = 0,
) -> List[dict]:
    """Run DSR + k-fold (+ MinBTL) for every strategy. Returns summary rows."""
    summary_rows = []

    for key in strategy_keys:
        total_values = load_portfolio_history(key)
        if total_values is None:
            logger.warning("No portfolio_history.json for %s — skipping.", key)
            continue

        returns = total_values.pct_change().dropna()
        n_trials = n_trials_map.get(key, 2)

        # Infer periods_per_year and embargo_periods from the loaded data
        ppy = infer_periods_per_year(total_values.index)
        embargo_periods_key = round(embargo_days * ppy / 365.25) if embargo_days else 0

        analysis = run_overfitting_analysis(
            strategy_key=key,
            strategy_returns=returns,
            return_matrix=None,
            param_grid={},
            periods_per_year=ppy,
            n_folds=n_folds,
            embargo_periods=embargo_periods_key,
        )

        # Override n_trials to the honest family/class-based estimate for
        # DSR and MinBTL (run_overfitting_analysis defaults to N=2 when no
        # return_matrix is supplied, since it has no other way to know how
        # many configurations were actually explored for this key).
        if analysis.dsr is not None:
            analysis.dsr = calculate_deflated_sharpe_ratio(
                returns=returns,
                n_trials=n_trials,
                periods_per_year=ppy,
            )
            analysis.n_param_combinations = n_trials
        if analysis.minbtl is not None:
            analysis.minbtl = calculate_minbtl(
                observed_sharpe_annualized=(
                    analysis.dsr.observed_sharpe
                    if analysis.dsr
                    else analysis.minbtl.observed_sharpe
                ),
                n_trials=n_trials,
                actual_years=analysis.minbtl.actual_years,
            )

        save_analysis(analysis, key)

        dsr_val = f"{analysis.dsr.dsr:.4f}" if analysis.dsr else "N/A"
        dsr_v = analysis.dsr.verdict if analysis.dsr else "N/A"
        kf_frac = f"{analysis.kfold.fraction_positive:.0%}" if analysis.kfold else "N/A"
        kf_v = analysis.kfold.verdict if analysis.kfold else "N/A"

        # Overall verdict
        verdicts = []
        if analysis.dsr:
            verdicts.append(analysis.dsr.verdict)
        if analysis.kfold:
            verdicts.append(analysis.kfold.verdict)
        if all(v == "PASS" for v in verdicts):
            overall = "PASS"
        elif any(v == "FAIL" for v in verdicts):
            overall = "FAIL"
        else:
            overall = "WARN" if verdicts else "N/A"

        summary_rows.append(
            {
                "strategy": key,
                "n_trials": n_trials,
                "dsr": dsr_val,
                "dsr_verdict": dsr_v,
                "kfold_frac_pos": kf_frac,
                "kfold_verdict": kf_v,
                "overall": overall,
            }
        )

    return summary_rows


def run_pbo_sweeps(
    n_folds: int,
    embargo_days: int = 0,
    walk_forward: bool = False,
) -> List[dict]:
    """
    Run full PBO sweeps for base strategy families.

    If ``walk_forward`` is True, also runs ``WalkForwardAnalysis`` on the
    same ``strategy_class``/``param_grid``/``underlying``/``prices`` already
    loaded for the PBO sweep, and attaches the result as the ``walkforward``
    section of that family's overfitting_analysis.json.
    """
    cache = HistoricalDataCache(cache_dir="data/cache")
    data_dict = {}
    for symbol in SYMBOLS:
        # Offline analysis: whatever history the cache has is what we sweep.
        # (The strict range-covering lookup missed everything once the cache
        # start drifted past 2015-01-01 — see load_best_cached_data.)
        df = cache.load_best_cached_data(symbol)
        if not df.empty:
            data_dict[symbol] = df
    if not data_dict:
        print("ERROR: No cached price data. Run: python scripts/run_backtest.py --all")
        return []

    from data import align_dataframes

    prices = align_dataframes(data_dict)
    underlying = [AssetStrategy(s, currency=CURRENCY) for s in SYMBOLS]
    lookback = 252
    backtest_start = prices.index[lookback]
    backtest_end = prices.index[-1]

    pbo_rows = []
    for family, cfg in PBO_PARAM_GRIDS.items():
        print(f"  PBO sweep: {family} ...")
        strategy_class = cfg["strategy_class"]
        param_grid = cfg["param_grid"]

        sweep = ParameterSweep(
            strategy_class=strategy_class,
            param_grid=param_grid,
            metric="sharpe_ratio",
            initial_capital=10_000.0,
            transaction_cost_bps=7.5,
            store_returns=True,
        )
        sweep_df = sweep.run(
            underlying=underlying,
            prices=prices,
            start_date=backtest_start,
            end_date=backtest_end,
            lookback_days=lookback,
        )
        if sweep_df.empty:
            print(f"  WARNING: Sweep returned no results for {family}.")
            continue

        return_matrix = sweep.get_return_matrix()
        best_key = next(iter(sweep.return_series_))
        best_values = sweep.return_series_[best_key]
        best_returns = best_values.pct_change().dropna()

        # Infer periods_per_year and embargo_periods from the sweep data
        ppy = infer_periods_per_year(best_values.index)
        embargo_periods_sweep = (
            round(embargo_days * ppy / 365.25) if embargo_days else 0
        )

        analysis = run_overfitting_analysis(
            strategy_key=f"{family}__pbo_sweep",
            strategy_returns=best_returns,
            return_matrix=return_matrix,
            param_grid=param_grid,
            periods_per_year=ppy,
            n_folds=n_folds,
            embargo_periods=embargo_periods_sweep,
        )

        wf_val = "N/A"
        wf_v = "N/A"
        if walk_forward:
            print(f"    Walk-forward: {family} ...")
            try:
                wfa = WalkForwardAnalysis(
                    strategy_class=strategy_class,
                    param_grid=param_grid,
                    metric="sharpe_ratio",
                    initial_capital=10_000.0,
                    transaction_cost_bps=7.5,
                )
                wf_results = wfa.run(underlying=underlying, prices=prices)
                if wf_results.windows:
                    analysis.walkforward = build_walk_forward_result(wf_results)
                    wf_val = f"{analysis.walkforward.overfitting_ratio}"
                    wf_v = analysis.walkforward.verdict
                else:
                    print(f"    WARNING: no walk-forward windows for {family}.")
            except Exception as exc:
                print(f"    WARNING: walk-forward failed for {family}: {exc}")

        save_analysis(analysis, f"{family}__pbo_sweep")

        pbo_val = f"{analysis.pbo.pbo:.4f}" if analysis.pbo else "N/A"
        pbo_v = analysis.pbo.verdict if analysis.pbo else "N/A"
        dsr_val = f"{analysis.dsr.dsr:.4f}" if analysis.dsr else "N/A"
        dsr_v = analysis.dsr.verdict if analysis.dsr else "N/A"
        kf_frac = f"{analysis.kfold.fraction_positive:.0%}" if analysis.kfold else "N/A"
        kf_v = analysis.kfold.verdict if analysis.kfold else "N/A"

        row = {
            "family": family,
            "n_configs": return_matrix.shape[1],
            "dsr": dsr_val,
            "dsr_verdict": dsr_v,
            "kfold_frac_pos": kf_frac,
            "kfold_verdict": kf_v,
            "pbo": pbo_val,
            "pbo_verdict": pbo_v,
        }
        if walk_forward:
            row["wf_ratio"] = wf_val
            row["wf_verdict"] = wf_v
        pbo_rows.append(row)

    return pbo_rows


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


def run_spa_analysis(strategy_keys, results_dir) -> None:
    """White's RC / Hansen's SPA across all strategies vs the equal_weight benchmark.

    Writes results/spa_analysis.json and a per-strategy ``spa`` stub (the p-values
    plus this strategy's mean-differential rank) into each overfitting_analysis.json.
    """
    import json as _json

    from analytics.family_matrix import build_family_return_matrix
    from analytics.spa import compute_spa

    matrix = build_family_return_matrix(results_dir, strategy_keys)
    if matrix.empty or matrix.shape[1] < 2:
        print("  SPA skipped: need >= 2 strategies with aligned history.")
        return

    bench_col = "equal_weight" if "equal_weight" in matrix.columns else None
    if bench_col is None:
        benchmark = matrix.mean(axis=1)
        strat_matrix = matrix
        print("  SPA: no equal_weight column; using cross-sectional mean benchmark.")
    else:
        benchmark = matrix[bench_col]
        strat_matrix = matrix.drop(columns=[bench_col])

    result = compute_spa(strat_matrix, benchmark, expected_block=3, n_iter=1000, seed=0)

    spa_dict = result.to_dict()
    out_path = Path(results_dir) / "spa_analysis.json"
    with open(out_path, "w") as f:
        _json.dump(spa_dict, f, indent=2)

    # Per-strategy stub: rank by mean differential vs benchmark.
    diffs = (
        strat_matrix.sub(benchmark, axis=0).mean(axis=0).sort_values(ascending=False)
    )
    ranks = {k: i + 1 for i, k in enumerate(diffs.index)}
    for key in strat_matrix.columns:
        opath = schema_strategy_dir(RESULTS_DIR.parent, key) / OVERFITTING_FILE
        payload = _json.load(open(opath)) if opath.exists() else {"strategy_key": key}
        payload["spa"] = {
            "reality_check_pvalue": spa_dict["reality_check_pvalue"],
            "spa_pvalue_consistent": spa_dict["spa_pvalue_consistent"],
            "best_strategy": spa_dict["best_strategy"],
            "rank": ranks.get(key),
            "n_strategies": spa_dict["n_strategies"],
        }
        opath.parent.mkdir(parents=True, exist_ok=True)
        with open(opath, "w") as f:
            _json.dump(payload, f, indent=2)

    print(f"\nSPA / Reality Check (N={result.n_strategies}, T={result.n_obs})")
    print(f"  Best strategy        : {result.best_strategy}")
    print(f"  Reality Check p-value: {result.reality_check_pvalue:.4f}")
    print(f"  SPA consistent p     : {result.spa_pvalue_consistent:.4f}")
    print(f"  Saved to             : {out_path}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Overfitting analysis: DSR + k-fold + PBO (batch or single strategy).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Batch mode: all strategies
  python scripts/run_all_overfitting.py --skip-pbo

  # Single strategy, Mode 1: sweep + overfitting
  python scripts/run_all_overfitting.py --strategy hrp --param linkage_method=single,complete,ward

  # Single strategy, Mode 2: DSR-only from existing results
  python scripts/run_all_overfitting.py --strategy hrp_ward --n-trials 3
        """,
    )
    parser.add_argument(
        "--strategy",
        type=str,
        default=None,
        help=(
            "BATCH: run for this strategy only (default: all). "
            "SINGLE: base strategy class (Mode 1) or results key (Mode 2)."
        ),
    )
    parser.add_argument(
        "--param",
        type=str,
        action="append",
        default=None,
        help="(Single strategy Mode 1) Parameter sweep grid: key=val1,val2,val3. Repeatable.",
    )
    parser.add_argument(
        "--n-trials",
        type=int,
        default=None,
        help="(Single strategy Mode 2) Number of trials N for DSR. Loads existing portfolio_history.json.",
    )
    parser.add_argument(
        "--s-subsets",
        type=int,
        default=16,
        help="CSCV partition count for PBO (default: 16, must be even).",
    )
    parser.add_argument(
        "--dsr-pass",
        type=float,
        default=0.95,
        dest="dsr_threshold_pass",
        help="DSR >= this is a PASS (default: 0.95).",
    )
    parser.add_argument(
        "--dsr-warn",
        type=float,
        default=0.80,
        dest="dsr_threshold_warn",
        help="DSR >= this is a WARN, else FAIL (default: 0.80).",
    )
    parser.add_argument(
        "--pbo-pass",
        type=float,
        default=0.30,
        dest="pbo_threshold_pass",
        help="PBO <= this is a PASS (default: 0.30).",
    )
    parser.add_argument(
        "--pbo-warn",
        type=float,
        default=0.50,
        dest="pbo_threshold_warn",
        help="PBO <= this is a WARN, else FAIL (default: 0.50).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="(Single strategy) Override output directory (default: results/strategies/<strategy>/).",
    )
    parser.add_argument(
        "--metric",
        type=str,
        default="sharpe_ratio",
        help="(Single strategy Mode 1) Sweep optimisation metric (default: sharpe_ratio).",
    )
    parser.add_argument(
        "--scenario-removal",
        action="store_true",
        help=(
            "(Single strategy Mode 2) Also run excise-mode leave-one-crisis-out scenario removal "
            "from the saved portfolio history and write stress_test.json."
        ),
    )
    parser.add_argument(
        "--method",
        choices=["dsr", "cpcv", "bootstrap"],
        default="dsr",
        help="(Single strategy) Analysis method: dsr (default), cpcv (combinatorial purged CV), or bootstrap.",
    )
    parser.add_argument(
        "--cpcv-folds",
        type=int,
        default=6,
        help="(Single strategy, CPCV mode) Number of CPCV groups (default: 6).",
    )
    parser.add_argument(
        "--bootstrap-n",
        type=int,
        default=500,
        help="(Single strategy, Bootstrap mode) Block-bootstrap replications (default: 500).",
    )
    parser.add_argument(
        "--block-months",
        type=int,
        default=3,
        help="(Single strategy, Bootstrap mode) Expected bootstrap block length in months (default: 3).",
    )
    parser.add_argument(
        "--bootstrap-fast",
        action="store_true",
        help="(Single strategy, Bootstrap mode) Resample realised strategy returns instead of re-running backtests.",
    )
    parser.add_argument(
        "--skip-pbo",
        action="store_true",
        help="(Batch mode) Skip PBO parameter sweeps (DSR + k-fold only, much faster).",
    )
    parser.add_argument(
        "--n-folds",
        type=int,
        default=10,
        help="(Batch mode) Number of k-fold time splits (default: 10).",
    )
    parser.add_argument(
        "--embargo-days",
        type=int,
        default=0,
        help=(
            "Purge/embargo window for k-fold stability, in calendar days "
            "(converted to periods via inferred periods_per_year; default: 0 = "
            "classic k-fold)."
        ),
    )
    parser.add_argument(
        "--walk-forward",
        action="store_true",
        help=(
            "(Batch mode) Also run walk-forward analysis for PBO_PARAM_GRIDS families "
            "(reuses the same price data/grid as the PBO sweep). Ignored "
            "if --skip-pbo is set."
        ),
    )
    parser.add_argument(
        "--composed-pbo",
        action="store_true",
        help=(
            "(Batch mode) Also run group PBO for composed/overlay strategy families "
            "(e.g. vol-target variants of the same base strategy) that "
            "don't otherwise get a PBO from a ParameterSweep."
        ),
    )
    parser.add_argument(
        "--spa",
        action="store_true",
        help=(
            "(Batch mode) Run White's Reality Check / Hansen's SPA across all strategies vs "
            "the equal_weight benchmark; write results/spa_analysis.json."
        ),
    )
    parser.add_argument(
        "--battery",
        action="store_true",
        help=(
            "(Batch mode) Also run the per-strategy validation battery (DSR/MinBTL/CPCV/"
            "bootstrap) by delegating to scripts/validate_strategy.py --all, "
            "so one command covers both analyses. For the full pipeline "
            "(backtests included) prefer scripts/run_full_analysis.py."
        ),
    )
    args = parser.parse_args()

    # ======================================================================== #
    # SINGLE STRATEGY MODE (Mode 1 & Mode 2)
    # ======================================================================== #
    if args.param or args.n_trials:
        if not args.strategy:
            parser.error(
                "Single strategy mode requires --strategy (base class for Mode 1, "
                "or results key for Mode 2)."
            )

        # Special analysis methods (CPCV, Bootstrap)
        if args.method == "cpcv":
            run_cpcv_analysis(args.strategy, args.cpcv_folds, args.embargo_days)
            return
        if args.method == "bootstrap":
            run_bootstrap_analysis(
                args.strategy, args.bootstrap_n, args.block_months, args.bootstrap_fast
            )
            return

        # Validate mode selection
        if args.param and args.n_trials:
            parser.error(
                "Specify either --param (Mode 1) or --n-trials (Mode 2), not both."
            )
        if args.scenario_removal and args.param:
            parser.error(
                "--scenario-removal is Mode 2 only; use it with --n-trials, not --param."
            )

        print(f"\nOVERFITTING ANALYSIS — {args.strategy}")
        print(
            f"Mode: {'Sweep + Overfitting' if args.param else 'DSR-only (existing results)'}"
        )

        if args.param:
            # ================================================================ #
            # Mode 1: param sweep + DSR + PBO + k-fold
            # ================================================================ #
            if args.strategy not in STRATEGY_CLASSES:
                print(
                    f"\nERROR: Unknown strategy class '{args.strategy}'.\n"
                    f"Available: {', '.join(STRATEGY_CLASSES.keys())}\n"
                    "For composed/overlay strategies use Mode 2 (--n-trials)."
                )
                sys.exit(1)

            param_grid: dict = {}
            for p in args.param:
                k, vals = parse_param(p)
                param_grid[k] = vals

            print(f"Parameter grid: {param_grid}\n")

            logger.info("Loading cached price data...")
            prices = load_cached_prices()
            logger.info(f"Loaded {len(prices)} days for {list(prices.columns)}")

            underlying = [AssetStrategy(s, currency=CURRENCY) for s in SYMBOLS]
            lookback = 252
            backtest_start = prices.index[lookback]
            backtest_end = prices.index[-1]

            strategy_class = STRATEGY_CLASSES[args.strategy]
            sweep = ParameterSweep(
                strategy_class=strategy_class,
                param_grid=param_grid,
                metric=args.metric,
                initial_capital=10_000.0,
                transaction_cost_bps=7.5,
                store_returns=True,
            )

            logger.info("Running parameter sweep...")
            sweep_df = sweep.run(
                underlying=underlying,
                prices=prices,
                start_date=backtest_start,
                end_date=backtest_end,
                lookback_days=lookback,
            )

            if sweep_df.empty:
                print("ERROR: Parameter sweep returned no results. Check your param grid.")
                sys.exit(1)

            print(f"Sweep complete: {len(sweep_df)} successful combinations.\n")

            return_matrix = sweep.get_return_matrix()

            # Best-performing combo returns (by target metric)
            best_key = next(iter(sweep.return_series_))
            best_params = {
                k: v
                for k, v in zip(
                    sweep_df.columns[: len(param_grid)], sweep_df.iloc[0][: len(param_grid)]
                )
            }
            best_frozen = frozenset(best_params.items())
            if best_frozen in sweep.return_series_:
                best_values = sweep.return_series_[best_frozen]
            else:
                best_values = sweep.return_series_[best_key]

            best_returns = best_values.pct_change().dropna()
            strategy_key = args.strategy

            # Infer periods_per_year and embargo_periods from the returns
            ppy = infer_periods_per_year(best_values.index)
            embargo_periods = (
                round(args.embargo_days * ppy / 365.25) if args.embargo_days else 0
            )

            analysis = run_overfitting_analysis(
                strategy_key=strategy_key,
                strategy_returns=best_returns,
                return_matrix=return_matrix,
                param_grid=param_grid,
                periods_per_year=ppy,
                s_subsets=args.s_subsets,
                dsr_threshold_pass=args.dsr_threshold_pass,
                dsr_threshold_warn=args.dsr_threshold_warn,
                pbo_threshold_pass=args.pbo_threshold_pass,
                pbo_threshold_warn=args.pbo_threshold_warn,
                embargo_periods=embargo_periods,
            )

        else:
            # ================================================================ #
            # Mode 2: DSR-only from existing portfolio_history.json
            # ================================================================ #
            strategy_key = args.strategy
            print(f"Loading portfolio history for '{strategy_key}'...\n")

            total_values = load_portfolio_history(strategy_key)
            if total_values is None:
                logger.error(
                    f"No portfolio_history.json found for {strategy_key}.\n"
                    "Run a backtest first: python scripts/run_backtest.py --all"
                )
                sys.exit(1)
            best_returns = total_values.pct_change().dropna()

            # Infer periods_per_year and embargo_periods from the loaded data
            ppy = infer_periods_per_year(total_values.index)
            embargo_periods = (
                round(args.embargo_days * ppy / 365.25) if args.embargo_days else 0
            )

            analysis = run_overfitting_analysis(
                strategy_key=strategy_key,
                strategy_returns=best_returns,
                return_matrix=None,  # PBO skipped in Mode 2
                param_grid={},
                periods_per_year=ppy,
                s_subsets=args.s_subsets,
                dsr_threshold_pass=args.dsr_threshold_pass,
                dsr_threshold_warn=args.dsr_threshold_warn,
                pbo_threshold_pass=args.pbo_threshold_pass,
                pbo_threshold_warn=args.pbo_threshold_warn,
                embargo_periods=embargo_periods,
            )

            # Override n_trials to user-supplied value for DSR
            if analysis.dsr is not None:
                from analytics.overfitting import calculate_deflated_sharpe_ratio

                analysis.dsr = calculate_deflated_sharpe_ratio(
                    returns=best_returns,
                    n_trials=args.n_trials,
                    periods_per_year=ppy,
                    threshold_pass=args.dsr_threshold_pass,
                    threshold_warn=args.dsr_threshold_warn,
                )
            analysis.n_param_combinations = args.n_trials

        print_analysis_report(analysis)

        out_path = save_analysis(analysis, strategy_key)
        print(f"Results saved to: {out_path}\n")

        if args.scenario_removal:
            import json as _json

            from analytics.stress_testing import run_stress_test

            total_values = load_portfolio_history(strategy_key)
            if total_values is not None:
                report = run_stress_test(total_values, strategy_key)
                stress_path = (
                    schema_strategy_dir(RESULTS_DIR.parent, strategy_key) / "stress_test.json"
                )
                stress_path.parent.mkdir(parents=True, exist_ok=True)
                with open(stress_path, "w") as f:
                    _json.dump(report.to_dict(), f, indent=2)
                print(f"Scenario removal (excise) saved to: {stress_path}\n")

        return

    # ======================================================================== #
    # BATCH MODE (default)
    # ======================================================================== #
    if args.battery:
        import subprocess

        battery_cmd = [
            sys.executable,
            str(Path(__file__).parent / "validate_strategy.py"),
        ]
        battery_cmd += ["--strategy", args.strategy] if args.strategy else ["--all"]
        print("Running validation battery (validate_strategy.py) ...")
        rc = subprocess.run(battery_cmd).returncode
        if rc != 0:
            print(f"WARNING: validation battery exited {rc}; continuing.")

    # Discover strategy keys
    if args.strategy:
        strategy_keys = [args.strategy]
    else:
        strategy_keys = sorted(
            d.name
            for d in RESULTS_DIR.iterdir()
            if d.is_dir()
            and (d / STRATEGY_FILES["portfolio_history"]).exists()
            and not d.name.endswith("__pbo_sweep")
        )

    if not strategy_keys:
        print(f"No strategies found in {RESULTS_DIR}. Run a backtest first.")
        sys.exit(1)

    print(f"\nBATCH OVERFITTING ANALYSIS")
    print(f"Strategies : {len(strategy_keys)}")
    print(f"K-Folds    : {args.n_folds}  (embargo_days={args.embargo_days})")
    print(f"PBO Sweeps : {'disabled' if args.skip_pbo else 'enabled'}")
    print(f"Walk-Fwd   : {'enabled' if args.walk_forward else 'disabled'}")
    print(f"Composed PBO: {'enabled' if args.composed_pbo else 'disabled'}")
    print()

    n_trials_map = build_n_trials_map(strategy_keys)

    # --- DSR + k-fold for all strategies ---
    print(f"Running DSR + k-fold for {len(strategy_keys)} strategies ...")
    summary_rows = run_dsr_kfold_batch(
        strategy_keys, args.n_folds, n_trials_map, embargo_days=args.embargo_days
    )

    print_summary_table(summary_rows)
    print("Summary:")
    print_verdict_counts(summary_rows, "dsr_verdict")
    print_verdict_counts(summary_rows, "kfold_verdict")
    print_verdict_counts(summary_rows, "overall")

    # --- PBO sweeps for base strategy families ---
    if not args.skip_pbo:
        print(f"\nRunning PBO sweeps for {len(PBO_PARAM_GRIDS)} strategy families ...")
        pbo_rows = run_pbo_sweeps(
            args.n_folds,
            embargo_days=args.embargo_days,
            walk_forward=args.walk_forward,
        )
        if pbo_rows:
            print("\nPBO Sweep Results:")
            print_summary_table(pbo_rows)

        if args.composed_pbo:
            print("\nRunning group PBO for composed/overlay strategy families ...")
            composed_rows = run_composed_pbo_groups(
                strategy_keys, RESULTS_DIR.parent, args.n_folds, save_analysis
            )
            if composed_rows:
                print("\nComposed PBO Group Results:")
                print_summary_table(composed_rows)
            else:
                print("  No composed groups with >= 4 usable members found.")

    if args.spa:
        print("\nRunning SPA / Reality Check across all strategies ...")
        run_spa_analysis(strategy_keys, RESULTS_DIR.parent)

    print(f"Results saved to: {RESULTS_DIR}/<strategy>/overfitting_analysis.json\n")


if __name__ == "__main__":
    main()
