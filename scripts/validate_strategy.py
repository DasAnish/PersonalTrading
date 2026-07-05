"""
CLI for the per-strategy validation battery (Phase 13).

Runs MinBTL -> DSR -> CPCV -> block bootstrap for a single saved strategy
and writes a single overall verdict. Pure composition over the existing
overfitting-analysis stack (analytics/validation.py); see that module for
the battery logic.

Usage:
    python scripts/validate_strategy.py --strategy hrp_ward
    python scripts/validate_strategy.py --strategy hrp_ward --n-trials 4
    python scripts/validate_strategy.py --strategy hrp_ward --json

Always writes results/strategies/<key>/validation.json.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analytics.validation import ValidationResult, run_validation_battery
from backtesting.results_schema import STRATEGY_FILES, strategy_dir

VALIDATION_FILENAME = "validation.json"
DEFAULT_RESULTS_DIR = "results"


def _format_value(v) -> str:
    if v is None:
        return "None"
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


def _format_values(values: dict) -> str:
    return " ".join(f"{k}={_format_value(v)}" for k, v in values.items())


def _discover_strategy_keys(results_dir: str, fallback: str) -> list:
    """Every strategy key with a saved portfolio_history.json, for n_trials sizing.

    Mirrors ``scripts/run_all_overfitting.py``'s discovery so the default
    ``--n-trials`` reflects the strategy's true family/sibling count across
    the whole results corpus, not just this one key.
    """
    strategies_root = Path(results_dir) / "strategies"
    if not strategies_root.exists():
        return [fallback]
    keys = sorted(
        d.name
        for d in strategies_root.iterdir()
        if d.is_dir()
        and (d / STRATEGY_FILES["portfolio_history"]).exists()
        and not d.name.endswith("__pbo_sweep")
    )
    if fallback not in keys:
        keys.append(fallback)
    return keys


def _resolve_n_trials(strategy: str, results_dir: str, quiet: bool) -> int:
    """Default --n-trials via ``run_all_overfitting.build_n_trials_map``."""
    from scripts.run_all_overfitting import build_n_trials_map

    strategy_keys = _discover_strategy_keys(results_dir, strategy)
    n_trials_map = build_n_trials_map(strategy_keys)
    if strategy in n_trials_map:
        return n_trials_map[strategy]
    if not quiet:
        print(f"NOTE: '{strategy}' not found in n_trials map; defaulting to 1.")
    return 1


def _print_table(result: ValidationResult) -> None:
    rows = [(t.name, _format_values(t.values), t.verdict) for t in result.tests]
    headers = ("TEST", "VALUES", "VERDICT")
    widths = [
        max(len(headers[i]), max((len(r[i]) for r in rows), default=0))
        for i in range(3)
    ]

    def _line(cols) -> str:
        return "  ".join(cols[i].ljust(widths[i]) for i in range(3))

    print(_line(headers))
    print(_line(["-" * w for w in widths]))
    for row in rows:
        print(_line(list(row)))
    print()
    print(f"OVERALL: {result.overall}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validation battery: MinBTL -> DSR -> CPCV -> block bootstrap.",
    )
    parser.add_argument("--strategy", type=str, required=True, help="Strategy key.")
    parser.add_argument(
        "--n-trials",
        type=int,
        default=None,
        help="Trials (N) for DSR/MinBTL (default: from build_n_trials_map).",
    )
    parser.add_argument(
        "--cpcv-folds", type=int, default=6, help="CPCV groups (default: 6)."
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
        "--embargo-days",
        type=int,
        default=10,
        help="CPCV purge/embargo window, calendar days (default: 10).",
    )
    parser.add_argument(
        "--results-dir",
        type=str,
        default=DEFAULT_RESULTS_DIR,
        help=f"Results root directory (default: {DEFAULT_RESULTS_DIR}).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a single-line JSON result as the last stdout line "
        "(suppresses the human-readable table).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    n_trials = args.n_trials
    if n_trials is None:
        n_trials = _resolve_n_trials(args.strategy, args.results_dir, quiet=args.json)

    try:
        result = run_validation_battery(
            strategy_key=args.strategy,
            results_dir=args.results_dir,
            n_trials=n_trials,
            cpcv_folds=args.cpcv_folds,
            bootstrap_n=args.bootstrap_n,
            block_months=args.block_months,
            embargo_days=args.embargo_days,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    out_path = strategy_dir(args.results_dir, args.strategy) / VALIDATION_FILENAME
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, indent=2)
        f.write("\n")

    if args.json:
        print(json.dumps(result.to_dict(), separators=(",", ":")))
    else:
        print(f"\nVALIDATION BATTERY — {args.strategy} (n_trials={n_trials})\n")
        _print_table(result)
        print(f"Saved to: {out_path}\n")


if __name__ == "__main__":
    main()
