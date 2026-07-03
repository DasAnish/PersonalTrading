"""
Standalone CLI to (re)generate per-strategy Markdown/HTML reports without
re-running a backtest.

Reads whatever result files already exist under
``results/strategies/<key>/`` (metrics.json always; stress_test.json and
overfitting_analysis.json optionally) via ``analytics.report.write_report``,
and writes ``report.md`` (and/or ``report.html``) back into that same
directory.

Usage:
    # Single strategy
    python scripts/generate_report.py --strategy hrp_ward

    # Every strategy in the index
    python scripts/generate_report.py --all

    # HTML too
    python scripts/generate_report.py --all --format both
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analytics.report import write_report
from backtesting.results_schema import INDEX_FILE, strategy_dir

RESULTS_DIR = Path("results")


def discover_strategy_keys(results_dir: Path) -> list:
    """Return all strategy keys with results, from strategies_index.json if
    present, else by scanning results/strategies/ for directories."""
    index_path = results_dir / INDEX_FILE
    if index_path.exists():
        import json

        try:
            with open(index_path, "r") as f:
                index_data = json.load(f)
            keys = sorted(index_data.get("strategies", {}).keys())
            if keys:
                return keys
        except Exception:
            pass

    strategies_dir = results_dir / "strategies"
    if not strategies_dir.exists():
        return []
    return sorted(d.name for d in strategies_dir.iterdir() if d.is_dir())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate static per-strategy backtest reports (Markdown/HTML) "
        "from existing results/ JSON — no backtest re-run required.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/generate_report.py --strategy hrp_ward
  python scripts/generate_report.py --all
  python scripts/generate_report.py --all --format both
        """,
    )
    parser.add_argument(
        "--strategy",
        type=str,
        default=None,
        help="Generate a report for this strategy key only.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Generate reports for every strategy in strategies_index.json "
        "(falls back to scanning results/strategies/ if the index is missing).",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["md", "html", "both"],
        default="md",
        help="Output format(s) to write (default: md).",
    )
    parser.add_argument(
        "--results-dir",
        type=str,
        default=str(RESULTS_DIR),
        help=f"Top-level results directory (default: {RESULTS_DIR}).",
    )

    args = parser.parse_args()

    if not args.strategy and not args.all:
        parser.error("Specify either --strategy <key> or --all.")
    if args.strategy and args.all:
        parser.error("Specify either --strategy or --all, not both.")

    results_dir = Path(args.results_dir)

    if args.strategy:
        strategy_keys = [args.strategy]
    else:
        strategy_keys = discover_strategy_keys(results_dir)

    if not strategy_keys:
        print(f"No strategies found under {results_dir}. Run a backtest first:")
        print("  python scripts/run_backtest.py --all")
        sys.exit(1)

    print(
        f"\nGenerating reports for {len(strategy_keys)} strategy(ies) — format={args.format}\n"
    )

    failures = []
    for key in strategy_keys:
        target_dir = strategy_dir(results_dir, key)
        if not target_dir.exists():
            print(f"  ✗ {key}: no results directory at {target_dir}")
            failures.append(key)
            continue
        try:
            written = write_report(key, results_dir, fmt=args.format)
            paths = ", ".join(str(p) for p in written.values() if p is not None)
            print(f"  ✓ {key}: {paths}")
        except Exception as exc:
            print(f"  ✗ {key}: failed — {exc}")
            failures.append(key)

    print()
    if failures:
        print(f"Completed with {len(failures)} failure(s): {', '.join(failures)}")
        sys.exit(1)
    print(
        f"All {len(strategy_keys)} report(s) generated under {results_dir}/strategies/<key>/"
    )


if __name__ == "__main__":
    main()
