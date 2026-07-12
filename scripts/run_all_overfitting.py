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

Pure analysis/IO/reporting logic lives in ``backtest_lib.overfitting_lib`` and
``backtest_lib.overfitting_batch_lib``; this file is CLI parsing + orchestration
only. Annualisation is always inferred (never hard-coded 252/12).
"""

import argparse
import logging
import sys
from pathlib import Path

# Project root + scripts dir on path so `analytics.*` and `backtest_lib.*`
# both resolve regardless of invocation (script, `run_all_overfitting`, or
# `scripts.run_all_overfitting`).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from analytics.composed_pbo import run_composed_pbo_groups  # noqa: E402
from analytics.metrics import infer_periods_per_year  # noqa: E402
from analytics.overfitting import (  # noqa: E402
    calculate_deflated_sharpe_ratio,
    run_overfitting_analysis,
)
from backtesting.results_schema import STRATEGY_FILES  # noqa: E402
from backtesting.results_schema import strategy_dir as schema_strategy_dir  # noqa: E402
from optimization import ParameterSweep  # noqa: E402
from strategies import AssetStrategy  # noqa: E402

from backtest_lib.overfitting_lib import (  # noqa: E402
    CURRENCY,
    RESULTS_DIR,
    STRATEGY_CLASSES,
    SYMBOLS,
    load_cached_prices,
    load_portfolio_history,
    parse_param,
    print_analysis_report,
    print_summary_table,
    print_verdict_counts,
    run_bootstrap_analysis,
    run_cpcv_analysis,
    save_analysis,
)

# Re-exported for tests (tests/test_overfitting_ext.py) and
# scripts/validate_strategy.py, which import these from run_all_overfitting.
from backtest_lib.overfitting_batch_lib import (  # noqa: E402,F401
    PBO_PARAM_GRIDS,
    build_n_trials_map,
    run_dsr_kfold_batch,
    run_pbo_sweeps,
    run_spa_analysis,
)

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
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
    return parser


def _run_single_strategy(args, parser: argparse.ArgumentParser) -> None:
    """Single-strategy path (Mode 1 sweep / Mode 2 DSR-only, plus cpcv/bootstrap)."""
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
        analysis, strategy_key = _analyze_sweep(args)
    else:
        analysis, strategy_key = _analyze_dsr_only(args)

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
                schema_strategy_dir(RESULTS_DIR.parent, strategy_key)
                / "stress_test.json"
            )
            stress_path.parent.mkdir(parents=True, exist_ok=True)
            with open(stress_path, "w") as f:
                _json.dump(report.to_dict(), f, indent=2)
            print(f"Scenario removal (excise) saved to: {stress_path}\n")


def _analyze_sweep(args):
    """Mode 1: param sweep + DSR + PBO + k-fold. Returns (analysis, strategy_key)."""
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
            sweep_df.columns[: len(param_grid)],
            sweep_df.iloc[0][: len(param_grid)],
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
    return analysis, strategy_key


def _analyze_dsr_only(args):
    """Mode 2: DSR-only from existing history. Returns (analysis, strategy_key)."""
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
        analysis.dsr = calculate_deflated_sharpe_ratio(
            returns=best_returns,
            n_trials=args.n_trials,
            periods_per_year=ppy,
            threshold_pass=args.dsr_threshold_pass,
            threshold_warn=args.dsr_threshold_warn,
        )
    analysis.n_param_combinations = args.n_trials
    return analysis, strategy_key


def _run_batch(args) -> None:
    """Batch path: DSR + k-fold for all strategies (+ optional PBO/composed/SPA)."""
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

    print("\nBATCH OVERFITTING ANALYSIS")
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


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    # Single strategy mode is selected by --param (Mode 1) or --n-trials (Mode 2);
    # otherwise run the default batch over all discovered strategies.
    if args.param or args.n_trials:
        _run_single_strategy(args, parser)
        return

    _run_batch(args)


if __name__ == "__main__":
    main()
