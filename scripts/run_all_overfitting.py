"""
Batch overfitting analysis for all strategy results.

Runs DSR + k-fold temporal stability for every strategy in results/strategies/.
Optionally runs PBO parameter sweeps for base strategy families, walk-forward
analysis for those same families, and group PBO for composed/overlay
strategy families (Phase 6).

Usage:
  # Fast: DSR + k-fold only (no parameter sweeps)
  python scripts/run_all_overfitting.py --skip-pbo

  # Single strategy
  python scripts/run_all_overfitting.py --strategy hrp_ward --skip-pbo

  # Full: includes PBO sweeps for base families (slow ~10 min)
  python scripts/run_all_overfitting.py

  # Custom fold count
  python scripts/run_all_overfitting.py --skip-pbo --n-folds 5

  # Purged/embargoed k-fold (embargo expressed in calendar days)
  python scripts/run_all_overfitting.py --skip-pbo --embargo-days 30

  # Also run walk-forward analysis for PBO_PARAM_GRIDS families
  python scripts/run_all_overfitting.py --walk-forward

  # Also run group PBO for composed/overlay strategy families
  python scripts/run_all_overfitting.py --composed-pbo
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
    embargo_periods: int = 0,
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

        analysis = run_overfitting_analysis(
            strategy_key=key,
            strategy_returns=returns,
            return_matrix=None,
            param_grid={},
            periods_per_year=12,
            n_folds=n_folds,
            embargo_periods=embargo_periods,
        )

        # Override n_trials to the honest family/class-based estimate for
        # DSR and MinBTL (run_overfitting_analysis defaults to N=2 when no
        # return_matrix is supplied, since it has no other way to know how
        # many configurations were actually explored for this key).
        if analysis.dsr is not None:
            analysis.dsr = calculate_deflated_sharpe_ratio(
                returns=returns,
                n_trials=n_trials,
                periods_per_year=12,
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
    embargo_periods: int = 0,
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
        df = cache.load_cached_data(
            symbol,
            pd.Timestamp("2015-01-01"),
            pd.Timestamp.now(),
            max_age_days=30,
        )
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
        best_returns = sweep.return_series_[best_key].pct_change().dropna()

        analysis = run_overfitting_analysis(
            strategy_key=f"{family}__pbo_sweep",
            strategy_returns=best_returns,
            return_matrix=return_matrix,
            param_grid=param_grid,
            periods_per_year=12,
            n_folds=n_folds,
            embargo_periods=embargo_periods,
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
        description="Batch overfitting analysis (DSR + k-fold) for all strategies.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--strategy",
        type=str,
        default=None,
        help="Run for a single strategy key only (default: all).",
    )
    parser.add_argument(
        "--skip-pbo",
        action="store_true",
        help="Skip PBO parameter sweeps (DSR + k-fold only, much faster).",
    )
    parser.add_argument(
        "--n-folds",
        type=int,
        default=10,
        help="Number of k-fold time splits (default: 10).",
    )
    parser.add_argument(
        "--embargo-days",
        type=int,
        default=0,
        help=(
            "Purge/embargo window for k-fold stability, in calendar days "
            "(converted to periods via periods_per_year=12; default: 0 = "
            "classic k-fold)."
        ),
    )
    parser.add_argument(
        "--walk-forward",
        action="store_true",
        help=(
            "Also run walk-forward analysis for PBO_PARAM_GRIDS families "
            "(reuses the same price data/grid as the PBO sweep). Ignored "
            "if --skip-pbo is set."
        ),
    )
    parser.add_argument(
        "--composed-pbo",
        action="store_true",
        help=(
            "Also run group PBO for composed/overlay strategy families "
            "(e.g. vol-target variants of the same base strategy) that "
            "don't otherwise get a PBO from a ParameterSweep."
        ),
    )
    parser.add_argument(
        "--spa",
        action="store_true",
        help=(
            "Run White's Reality Check / Hansen's SPA across all strategies vs "
            "the equal_weight benchmark; write results/spa_analysis.json."
        ),
    )
    parser.add_argument(
        "--battery",
        action="store_true",
        help=(
            "Also run the per-strategy validation battery (DSR/MinBTL/CPCV/"
            "bootstrap) by delegating to scripts/validate_strategy.py --all, "
            "so one command covers both analyses. For the full pipeline "
            "(backtests included) prefer scripts/run_full_analysis.py."
        ),
    )
    args = parser.parse_args()

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

    # embargo-days -> periods, using the monthly (periods_per_year=12)
    # rebalance cadence run_dsr_kfold_batch / run_pbo_sweeps operate on.
    embargo_periods = round(args.embargo_days * 12 / 365.25) if args.embargo_days else 0

    print(f"\nBATCH OVERFITTING ANALYSIS")
    print(f"Strategies : {len(strategy_keys)}")
    print(f"K-Folds    : {args.n_folds}  (embargo_periods={embargo_periods})")
    print(f"PBO Sweeps : {'disabled' if args.skip_pbo else 'enabled'}")
    print(f"Walk-Fwd   : {'enabled' if args.walk_forward else 'disabled'}")
    print(f"Composed PBO: {'enabled' if args.composed_pbo else 'disabled'}")
    print()

    n_trials_map = build_n_trials_map(strategy_keys)

    # --- DSR + k-fold for all strategies ---
    print(f"Running DSR + k-fold for {len(strategy_keys)} strategies ...")
    summary_rows = run_dsr_kfold_batch(
        strategy_keys, args.n_folds, n_trials_map, embargo_periods=embargo_periods
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
            embargo_periods=embargo_periods,
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
