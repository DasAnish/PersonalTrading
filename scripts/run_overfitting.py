"""
CLI script for overfitting analysis using Deflated Sharpe Ratio (DSR)
and Probability of Backtest Overfitting (PBO).

Two modes:

  Mode 1 — Sweep + Overfitting (recommended):
    Runs a parameter sweep with store_returns=True, then computes DSR and PBO.
    Requires: --strategy <base_class> --param <key=v1,v2,...>

    python scripts/run_overfitting.py \\
        --strategy hrp \\
        --param linkage_method=single,complete,ward

    python scripts/run_overfitting.py \\
        --strategy trend_following \\
        --param lookback_days=126,252,504 \\
        --param half_life_days=30,60,90

  Mode 2 — DSR-only from existing backtest results:
    Loads portfolio_history.json for a strategy and computes DSR only.
    Requires: --strategy <strategy_key> --n-trials <N>

    python scripts/run_overfitting.py --strategy hrp_ward --n-trials 3

Results are saved to results/strategies/<strategy_key>/overfitting_analysis.json.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from analytics.metrics import infer_periods_per_year  # noqa: E402
from analytics.overfitting import (
    run_overfitting_analysis,
    overfitting_analysis_to_dict,
    OverfittingAnalysis,
)
from backtesting.results_schema import (
    OVERFITTING_FILE,
    STRATEGY_FILES,
    STRESS_TEST_FILE,
    load_portfolio_values,
)
from backtesting.results_schema import strategy_dir as schema_strategy_dir
from data import HistoricalDataCache, align_dataframes
from optimization import ParameterSweep
from strategies import (
    HRPStrategy,
    TrendFollowingStrategy,
    EqualWeightStrategy,
    MinimumVarianceStrategy,
    RiskParityStrategy,
    MomentumTopNStrategy,
    AssetStrategy,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

STRATEGY_CLASSES = {
    "hrp": HRPStrategy,
    "trend_following": TrendFollowingStrategy,
    "equal_weight": EqualWeightStrategy,
    "minimum_variance": MinimumVarianceStrategy,
    "risk_parity": RiskParityStrategy,
    "momentum": MomentumTopNStrategy,
}

CURRENCY = "GBP"
SYMBOLS = sorted(
    p.stem.upper()
    for p in (Path(__file__).parent.parent / "strategy_definitions" / "assets").glob(
        "*.json"
    )
)
RESULTS_DIR = Path("results/strategies")


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


def load_portfolio_history(strategy_key: str) -> pd.Series:
    """
    Load portfolio total_value series from results/strategies/<key>/portfolio_history.json.

    Returns a pd.Series of total_value indexed by date.
    """
    path = (
        schema_strategy_dir(RESULTS_DIR.parent, strategy_key)
        / STRATEGY_FILES["portfolio_history"]
    )
    if not path.exists():
        logger.error(
            f"No portfolio_history.json found at {path}.\n"
            "Run a backtest first: python scripts/run_backtest.py --all"
        )
        sys.exit(1)

    return load_portfolio_values(RESULTS_DIR.parent, strategy_key)


def save_analysis(
    analysis: OverfittingAnalysis, strategy_key: str, output_dir: str | None
) -> Path:
    """Save overfitting_analysis.json to the strategy's results directory."""
    if output_dir:
        out_path = Path(output_dir) / OVERFITTING_FILE
    else:
        out_path = (
            schema_strategy_dir(RESULTS_DIR.parent, strategy_key) / OVERFITTING_FILE
        )

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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Overfitting analysis: Deflated Sharpe Ratio + Probability of Backtest Overfitting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Mode 1: run sweep + overfitting in one pass
  python scripts/run_overfitting.py --strategy hrp --param linkage_method=single,complete,ward

  # Mode 2: DSR-only from existing backtest results (N=3 trials)
  python scripts/run_overfitting.py --strategy hrp_ward --n-trials 3

  # Custom thresholds
  python scripts/run_overfitting.py --strategy hrp --param linkage_method=single,complete,ward \\
      --dsr-pass 0.90 --pbo-pass 0.40
        """,
    )

    parser.add_argument(
        "--strategy",
        type=str,
        required=True,
        help=(
            "Mode 1: base strategy class key (hrp, trend_following, …). "
            "Mode 2: full strategy results key (hrp_ward, trend_following, …)."
        ),
    )
    parser.add_argument(
        "--param",
        type=str,
        action="append",
        default=None,
        help="Parameter sweep grid entry: key=val1,val2,val3. Repeatable. Activates Mode 1.",
    )
    parser.add_argument(
        "--n-trials",
        type=int,
        default=None,
        help="(Mode 2) Number of trials N for DSR. Loads existing portfolio_history.json.",
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
        help="Override output directory (default: results/strategies/<strategy>/).",
    )
    parser.add_argument(
        "--metric",
        type=str,
        default="sharpe_ratio",
        help="Sweep optimisation metric (default: sharpe_ratio).",
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
        "--scenario-removal",
        action="store_true",
        help=(
            "Also run excise-mode leave-one-crisis-out scenario removal from "
            "the saved portfolio history and write stress_test.json "
            "(Mode 2 only)."
        ),
    )
    parser.add_argument(
        "--method",
        choices=["dsr", "cpcv", "bootstrap"],
        default="dsr",
        help="Analysis method: dsr (default, DSR/PBO/k-fold via --param/--n-trials), "
        "cpcv (combinatorial purged CV), or bootstrap (Phase 9).",
    )
    parser.add_argument(
        "--cpcv-folds",
        type=int,
        default=6,
        help="Number of CPCV groups (default: 6). Test combinations = C(folds, 2).",
    )
    parser.add_argument(
        "--bootstrap-n",
        type=int,
        default=500,
        help="Block-bootstrap replications (default: 500).",
    )
    parser.add_argument(
        "--block-months",
        type=int,
        default=3,
        help="Expected bootstrap block length in months (default: 3).",
    )
    parser.add_argument(
        "--bootstrap-fast",
        action="store_true",
        help="Resample realised strategy returns instead of re-running backtests.",
    )

    args = parser.parse_args()

    if args.method == "cpcv":
        run_cpcv_analysis(args.strategy, args.cpcv_folds, args.embargo_days)
        return
    if args.method == "bootstrap":
        run_bootstrap_analysis(
            args.strategy, args.bootstrap_n, args.block_months, args.bootstrap_fast
        )
        return

    # Validate mode
    if args.param and args.n_trials:
        parser.error(
            "Specify either --param (Mode 1) or --n-trials (Mode 2), not both."
        )
    if not args.param and not args.n_trials:
        parser.error("Specify either --param (Mode 1) or --n-trials (Mode 2).")
    if args.scenario_removal and args.param:
        parser.error(
            "--scenario-removal is Mode 2 only; use it with --n-trials, not --param."
        )

    print(f"\nOVERFITTING ANALYSIS — {args.strategy}")
    print(
        f"Mode: {'Sweep + Overfitting' if args.param else 'DSR-only (existing results)'}"
    )

    if args.param:
        # ------------------------------------------------------------------ #
        # Mode 1: param sweep + DSR + PBO
        # ------------------------------------------------------------------ #
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
        # Find which frozenset corresponds to the best row in sweep_df
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
            # Fall back to first stored series
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
        # ------------------------------------------------------------------ #
        # Mode 2: DSR-only from existing portfolio_history.json
        # ------------------------------------------------------------------ #
        strategy_key = args.strategy
        print(f"Loading portfolio history for '{strategy_key}'...\n")

        total_values = load_portfolio_history(strategy_key)
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

    out_path = save_analysis(analysis, strategy_key, args.output_dir)
    print(f"Results saved to: {out_path}\n")

    if args.scenario_removal:
        import json as _json

        from analytics.stress_testing import run_stress_test

        total_values = load_portfolio_history(strategy_key)
        report = run_stress_test(total_values, strategy_key)
        stress_path = (
            schema_strategy_dir(RESULTS_DIR.parent, strategy_key) / STRESS_TEST_FILE
        )
        stress_path.parent.mkdir(parents=True, exist_ok=True)
        with open(stress_path, "w") as f:
            _json.dump(report.to_dict(), f, indent=2)
        print(f"Scenario removal (excise) saved to: {stress_path}\n")


if __name__ == "__main__":
    main()
