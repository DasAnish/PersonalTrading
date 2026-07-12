#!/usr/bin/env python3
"""
Comprehensive analysis + optional dashboard.

Runs the full library-wide pipeline in order:

  1. [Optional] Start Flask dashboard          (--dashboard)
  2. [Optional] Refresh market data from IB    (--refresh)
  3. Backtest every strategy definition        (scripts/run_backtest.py --all)
  4. Per-strategy validation battery           (scripts/validate_strategy.py --all)
     (MinBTL, DSR, CPCV, block bootstrap -> validation.json per strategy)
  5. [Optional] Mechanism coverage analysis    (scripts/tag_mechanisms.py --coverage)
  6. Library-wide overfitting + SPA            (scripts/run_all_overfitting.py --spa ...)
     (DSR/k-fold per strategy, PBO sweeps + walk-forward per base family,
      group PBO for composed/overlay families, SPA across the library)
  7. [Optional] Static reports                 (scripts/generate_report.py --all --format both)

SPA (step 6) corrects for having *tried many strategies*. Per-strategy battery
(step 4) judges each strategy in isolation; SPA judges the whole family for
data-snooping and writes results/spa_analysis.json.

This script never places, submits, modifies, or cancels any trade order.

Usage:
  python scripts/run_full_analysis.py                           # minimal pipeline
  python scripts/run_full_analysis.py --refresh --coverage --reports --dashboard
  python scripts/run_full_analysis.py --skip-backtest           # reuse existing results/
  python scripts/run_full_analysis.py --fast                    # skip PBO / walk-forward
  python scripts/run_full_analysis.py --skip-validate           # SPA/overfitting only

Exit code is non-zero if any fatal step fails (backtest, validate).
Non-fatal steps (coverage, reports) do not block subsequent steps.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
DASHBOARD_URL = "http://localhost:5000"


def _start_dashboard() -> subprocess.Popen:
    """Spin off Flask dashboard as detached child process."""
    proc = subprocess.Popen(
        [sys.executable, str(SCRIPTS_DIR / "serve_results.py")],
        cwd=str(REPO_ROOT),
    )
    time.sleep(3)  # give Flask time to bind
    print(
        f"Dashboard: {DASHBOARD_URL} (pid {proc.pid}) — refresh as steps "
        "complete. Keeps running after script exits; stop by killing port 5000."
    )
    return proc


def _run(label: str, cmd: list[str], *, fatal: bool = True) -> bool:
    """Run one step, streaming output. Returns True on success.

    Args:
        label: Step name for printing
        cmd: Command list to run
        fatal: If True, raise SystemExit on failure; if False, return False

    Returns:
        True if success, False if failure (only when fatal=False)

    Raises:
        SystemExit if fatal=True and command fails
    """
    print("\n" + "=" * 70)
    print(f"[{label}] {' '.join(cmd)}")
    print("=" * 70, flush=True)
    start = time.time()
    result = subprocess.run(cmd, cwd=str(REPO_ROOT))
    elapsed = time.time() - start
    ok = result.returncode == 0
    status = "OK" if ok else f"FAILED (exit {result.returncode})"
    print(f"[{label}] {status} in {elapsed:.1f}s", flush=True)
    if not ok and fatal:
        raise SystemExit(
            f"[{label}] FAILED (exit {result.returncode}) after {elapsed:.1f}s"
        )
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backtest + validate + overfitting/SPA + optional dashboard/coverage/reports.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Start Flask dashboard server (runs in background).",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Force fresh price data from IB Gateway (skips cache).",
    )
    parser.add_argument(
        "--skip-backtest",
        action="store_true",
        help="Reuse existing results/ instead of re-running all backtests.",
    )
    parser.add_argument(
        "--skip-validate",
        action="store_true",
        help="Skip the per-strategy validation battery.",
    )
    parser.add_argument(
        "--skip-overfitting",
        action="store_true",
        help="Skip the library-wide overfitting + SPA step.",
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Run mechanism coverage analysis (non-fatal).",
    )
    parser.add_argument(
        "--reports",
        action="store_true",
        help="Generate static md/html reports for all strategies (non-fatal).",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help=(
            "Pass --skip-pbo to the overfitting step (DSR/k-fold + SPA only; "
            "skips PBO sweeps, walk-forward, and composed PBO)."
        ),
    )
    args = parser.parse_args()

    py = sys.executable
    steps: list[tuple[str, list[str], bool]] = []
    results: list[tuple[str, bool]] = []

    if args.dashboard:
        _start_dashboard()

    if not args.skip_backtest:
        backtest_cmd = [py, str(SCRIPTS_DIR / "run_backtest.py"), "--all"]
        if args.refresh:
            backtest_cmd.append("--refresh")
        steps.append(("backtest", backtest_cmd, True))

    if not args.skip_validate:
        steps.append(
            ("validate", [py, str(SCRIPTS_DIR / "validate_strategy.py"), "--all"], True)
        )

    if args.coverage:
        steps.append(
            (
                "coverage",
                [py, str(SCRIPTS_DIR / "tag_mechanisms.py"), "--coverage"],
                False,
            )
        )

    if not args.skip_overfitting:
        overfit_cmd = [py, str(SCRIPTS_DIR / "run_all_overfitting.py"), "--spa"]
        if args.fast:
            overfit_cmd.append("--skip-pbo")
        else:
            # Opt-in flags in run_all_overfitting.py; the full pipeline wants
            # the complete suite (PBO sweeps + walk-forward + composed PBO).
            overfit_cmd += ["--walk-forward", "--composed-pbo"]
        steps.append(("overfitting+SPA", overfit_cmd, True))

    if args.reports:
        steps.append(
            (
                "reports",
                [
                    py,
                    str(SCRIPTS_DIR / "generate_report.py"),
                    "--all",
                    "--format",
                    "both",
                ],
                False,
            )
        )

    if not steps:
        print("Nothing to do — all steps skipped.")
        return

    overall_start = time.time()
    for label, cmd, fatal in steps:
        results.append((label, _run(label, cmd, fatal=fatal)))

    print("\n" + "=" * 70)
    print("PIPELINE SUMMARY")
    print("=" * 70)
    for name, ok in results:
        status = "✓" if ok else "✗"
        print(f"  {status} {name.ljust(16)} {'OK' if ok else 'FAILED'}")
    print(f"\nTotal time: {time.time() - overall_start:.1f}s")
    print("Output:")
    print("  Per-strategy battery : results/strategies/<key>/validation.json")
    print("  Library-wide SPA     : results/spa_analysis.json")
    if args.dashboard:
        print(f"  Dashboard            : {DASHBOARD_URL}")
    print("=" * 70)


if __name__ == "__main__":
    main()
