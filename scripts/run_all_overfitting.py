"""
Batch overfitting analysis for all strategy results.

Runs DSR + k-fold temporal stability for every strategy in results/strategies/.
Optionally runs PBO parameter sweeps for base strategy families.

Usage:
  # Fast: DSR + k-fold only (no parameter sweeps)
  python scripts/run_all_overfitting.py --skip-pbo

  # Single strategy
  python scripts/run_all_overfitting.py --strategy hrp_ward --skip-pbo

  # Full: includes PBO sweeps for base families (slow ~10 min)
  python scripts/run_all_overfitting.py

  # Custom fold count
  python scripts/run_all_overfitting.py --skip-pbo --n-folds 5
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from analytics.overfitting import (
    OverfittingAnalysis,
    run_overfitting_analysis,
    overfitting_analysis_to_dict,
)
from data import HistoricalDataCache, align_dataframes
from optimization import ParameterSweep
from strategies import (
    AssetStrategy,
    HRPStrategy,
    TrendFollowingStrategy,
    EqualWeightStrategy,
    MinimumVarianceStrategy,
    RiskParityStrategy,
    MomentumTopNStrategy,
)

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

RESULTS_DIR = Path("results/strategies")
CURRENCY = "GBP"
SYMBOLS = sorted(
    p.stem.upper()
    for p in (Path(__file__).parent.parent / "strategy_definitions" / "assets").glob("*.json")
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
    path = RESULTS_DIR / strategy_key / "portfolio_history.json"
    if not path.exists():
        return None
    with open(path) as f:
        data = json.load(f)
    dates = [pd.Timestamp(row["date"]) for row in data]
    values = [float(row["total_value"]) for row in data]
    return pd.Series(values, index=dates, name="total_value")


def save_analysis(analysis: OverfittingAnalysis, strategy_key: str) -> Path:
    """Save overfitting_analysis.json to the strategy's results directory."""
    out_path = RESULTS_DIR / strategy_key / "overfitting_analysis.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    d = overfitting_analysis_to_dict(analysis)
    with open(out_path, "w") as f:
        json.dump(d, f, indent=2, default=str)
    return out_path


def build_n_trials_map(strategy_keys: List[str]) -> Dict[str, int]:
    """
    Estimate n_trials for DSR by counting how many strategies share each
    family prefix. E.g. hrp_ward, hrp_single, hrp_complete, hrp_average → 4.
    This is used as a proxy for how many configurations were explored.
    """
    # Count siblings sharing a 2-word prefix (e.g. "hrp" or "momentum")
    from collections import Counter

    prefix_counts: Counter = Counter()
    for key in strategy_keys:
        parts = key.split("_")
        prefix_counts[parts[0]] += 1

    n_trials_map: Dict[str, int] = {}
    for key in strategy_keys:
        prefix = key.split("_")[0]
        n_trials_map[key] = max(prefix_counts[prefix], 2)
    return n_trials_map


def run_dsr_kfold_batch(
    strategy_keys: List[str],
    n_folds: int,
    n_trials_map: Dict[str, int],
) -> List[dict]:
    """Run DSR + k-fold for every strategy. Returns list of summary rows."""
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
        )

        # Override n_trials to the family-based estimate for DSR
        if analysis.dsr is not None:
            from analytics.overfitting import calculate_deflated_sharpe_ratio

            analysis.dsr = calculate_deflated_sharpe_ratio(
                returns=returns,
                n_trials=n_trials,
                periods_per_year=12,
            )
            analysis.n_param_combinations = n_trials

        save_analysis(analysis, key)

        dsr_val = f"{analysis.dsr.dsr:.4f}" if analysis.dsr else "N/A"
        dsr_v = analysis.dsr.verdict if analysis.dsr else "N/A"
        kf_frac = (
            f"{analysis.kfold.fraction_positive:.0%}" if analysis.kfold else "N/A"
        )
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


def run_pbo_sweeps(n_folds: int) -> List[dict]:
    """Run full PBO sweeps for base strategy families."""
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
        )

        save_analysis(analysis, f"{family}__pbo_sweep")

        pbo_val = f"{analysis.pbo.pbo:.4f}" if analysis.pbo else "N/A"
        pbo_v = analysis.pbo.verdict if analysis.pbo else "N/A"
        dsr_val = f"{analysis.dsr.dsr:.4f}" if analysis.dsr else "N/A"
        dsr_v = analysis.dsr.verdict if analysis.dsr else "N/A"
        kf_frac = (
            f"{analysis.kfold.fraction_positive:.0%}" if analysis.kfold else "N/A"
        )
        kf_v = analysis.kfold.verdict if analysis.kfold else "N/A"

        pbo_rows.append(
            {
                "family": family,
                "n_configs": return_matrix.shape[1],
                "dsr": dsr_val,
                "dsr_verdict": dsr_v,
                "kfold_frac_pos": kf_frac,
                "kfold_verdict": kf_v,
                "pbo": pbo_val,
                "pbo_verdict": pbo_v,
            }
        )

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
    args = parser.parse_args()

    # Discover strategy keys
    if args.strategy:
        strategy_keys = [args.strategy]
    else:
        strategy_keys = sorted(
            d.name
            for d in RESULTS_DIR.iterdir()
            if d.is_dir() and (d / "portfolio_history.json").exists()
            and not d.name.endswith("__pbo_sweep")
        )

    if not strategy_keys:
        print(f"No strategies found in {RESULTS_DIR}. Run a backtest first.")
        sys.exit(1)

    print(f"\nBATCH OVERFITTING ANALYSIS")
    print(f"Strategies : {len(strategy_keys)}")
    print(f"K-Folds    : {args.n_folds}")
    print(f"PBO Sweeps : {'disabled' if args.skip_pbo else 'enabled'}")
    print()

    n_trials_map = build_n_trials_map(strategy_keys)

    # --- DSR + k-fold for all strategies ---
    print(f"Running DSR + k-fold for {len(strategy_keys)} strategies ...")
    summary_rows = run_dsr_kfold_batch(strategy_keys, args.n_folds, n_trials_map)

    print_summary_table(summary_rows)
    print("Summary:")
    print_verdict_counts(summary_rows, "dsr_verdict")
    print_verdict_counts(summary_rows, "kfold_verdict")
    print_verdict_counts(summary_rows, "overall")

    # --- PBO sweeps for base strategy families ---
    if not args.skip_pbo:
        print(f"\nRunning PBO sweeps for {len(PBO_PARAM_GRIDS)} strategy families ...")
        pbo_rows = run_pbo_sweeps(args.n_folds)
        if pbo_rows:
            print("\nPBO Sweep Results:")
            print_summary_table(pbo_rows)

    print(f"Results saved to: {RESULTS_DIR}/<strategy>/overfitting_analysis.json\n")


if __name__ == "__main__":
    main()
