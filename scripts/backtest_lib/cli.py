"""Argument parsing for the backtest CLI."""

import argparse

from strategies import STRATEGY_REGISTRY


def parse_args() -> argparse.Namespace:
    """Build the parser, parse argv, apply implications and validation."""
    parser = argparse.ArgumentParser(
        description="Run portfolio strategy backtest on UK ETFs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples (Run ALL Strategies - RECOMMENDED):
  python run_backtest.py --all                              # Run all strategies, separate result files
  python run_backtest.py --all --refresh                    # Force fresh data from IB

Examples (Single Strategy vs Benchmark - Traditional):
  python run_backtest.py --use-definitions --strategy trend_following --benchmark hrp_ward
  python run_backtest.py --use-definitions --composed-strategy trend_with_vol_12
  python run_backtest.py --strategy hrp --benchmark equal_weight
  python run_backtest.py --strategy equal_weight --benchmark hrp --refresh

List Available Strategies:
  python -c "from strategies.strategy_loader import StrategyLoader; loader = StrategyLoader(); loader.list_strategies()"
        """,
    )

    # Mode selection
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run ALL available strategies from strategy definitions and output separate results files. "
        "This is the recommended mode for comprehensive analysis.",
    )

    # Strategy loading mode
    parser.add_argument(
        "--use-definitions",
        action="store_true",
        help="Load strategies from YAML definitions (strategy_definitions/) instead of registry",
    )

    # Strategy selection
    parser.add_argument(
        "--strategy",
        type=str,
        default="hrp",
        help="Primary strategy to test (default: hrp). "
        "When --use-definitions is set, this is a YAML definition key (e.g., trend_following). "
        "Otherwise, this is a registry strategy name.",
    )

    parser.add_argument(
        "--benchmark",
        type=str,
        default="equal_weight",
        help="Benchmark strategy for comparison (default: equal_weight). "
        "When --use-definitions is set, this is a YAML definition key. "
        "Otherwise, this is a registry strategy name.",
    )

    parser.add_argument(
        "--composed-strategy",
        type=str,
        default=None,
        help="Use a composed strategy instead of primary/benchmark. "
        "Only works with --use-definitions. "
        "Example: --use-definitions --composed-strategy trend_with_vol_12",
    )

    # Data refresh flag
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Force fresh data from Interactive Brokers (skip cache). "
        "Useful for getting the latest market data.",
    )

    # Stress test flag
    parser.add_argument(
        "--stress-test",
        action="store_true",
        help="After running backtest(s), compute stress-period metrics and "
        "leave-one-crisis-out scenario removal. Saves stress_test.json "
        "alongside other result files (--all mode) or prints to stdout.",
    )
    parser.add_argument(
        "--scenario-removal",
        action="store_true",
        help="Run TRUE leave-one-crisis-out (rerun mode): drop each crisis "
        "window from the price data and re-run the backtest. Implies "
        "--stress-test. Writes rerun scenario_removal into stress_test.json.",
    )

    # Report generation flag
    parser.add_argument(
        "--report",
        action="store_true",
        help="After saving a strategy's results, generate report.md "
        "(analytics/report.py) alongside the other result files. "
        "Equivalent to running scripts/generate_report.py afterwards.",
    )

    # Parallelism for the --all batch backtest. Each strategy writes its own
    # results/strategies/<key>/ files and only reads the shared cache, so the
    # backtests parallelise across processes. 0 = auto (cpu_count-1), 1 = serial.
    parser.add_argument(
        "--jobs",
        type=int,
        default=0,
        help="Worker processes for the --all batch backtest "
        "(0 = auto/cpu_count-1, 1 = serial). Cross-strategy steps are unaffected.",
    )

    # Strategy-specific parameters (dynamically generated for registry mode)
    # Only add these if not using YAML definitions
    for strategy_key, config in STRATEGY_REGISTRY.items():
        for param_name, param_config in config.get("params", {}).items():
            arg_name = f'--{strategy_key}-{param_name.replace("_", "-")}'
            parser.add_argument(
                arg_name,
                type=param_config["type"],
                default=param_config.get("default"),
                choices=param_config.get("choices"),
                help=param_config.get("help", f"{param_name} for {strategy_key}"),
            )

    args = parser.parse_args()
    # --scenario-removal implies --stress-test (it produces the report).
    if getattr(args, "scenario_removal", False):
        args.stress_test = True

    # The registry default "hrp" has no YAML definition (the definition keys
    # are hrp_ward / hrp_average / ...), so remap it when definitions mode is
    # active and the user didn't override --strategy.
    if args.use_definitions and args.strategy == "hrp":
        args.strategy = "hrp_ward"

    # Validation
    if not args.all:
        # Only validate these if not running all strategies
        if args.composed_strategy is None and args.strategy == args.benchmark:
            parser.error(
                "Strategy and benchmark must be different (unless using --composed-strategy)"
            )

        if args.composed_strategy and not args.use_definitions:
            parser.error("--composed-strategy requires --use-definitions")

    return args
