"""
Full-scale pipeline run: dashboard up first, then data -> backtests ->
mechanism coverage -> validation battery, with optional SPA and reports.

The dashboard reads results/ from disk on every request, so it reflects each
step's output live as the run progresses — refresh the browser to see new
backtests and validation verdicts appear.

Steps (each is a subprocess call to the existing CLI, nothing reimplemented):
    1. Spin off `scripts/serve_results.py`   (skip with --no-dashboard)
    2. `run_backtest.py --all --use-definitions`   (add --refresh to force IB fetch)
    3. `tag_mechanisms.py --coverage`
    4. `validate_strategy.py --all`
    5. `run_all_overfitting.py --spa`         (only with --spa)
    6. `generate_report.py --all --format both`  (only with --reports)

Usage:
    python scripts/full_run.py                  # backtests + coverage + battery
    python scripts/full_run.py --refresh --spa --reports
    python scripts/full_run.py --no-dashboard

This script never places, submits, modifies, or cancels any trade order —
it only runs backtests and analysis and serves read-only results.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DASHBOARD_URL = "http://localhost:5000"


def _run_step(name: str, cmd: list, *, fatal: bool) -> bool:
    """Run one pipeline step; stream its output. Returns True on success."""
    print(f"\n{'=' * 70}\nSTEP: {name}\n  {' '.join(cmd)}\n{'=' * 70}", flush=True)
    started = time.time()
    proc = subprocess.run(cmd, cwd=REPO_ROOT)
    elapsed = time.time() - started
    ok = proc.returncode == 0
    status = "OK" if ok else f"FAILED (exit {proc.returncode})"
    print(f"\n-- {name}: {status} in {elapsed:.0f}s", flush=True)
    if not ok and fatal:
        print(f"Aborting: '{name}' is required for the steps that follow.")
        sys.exit(proc.returncode)
    return ok


def _start_dashboard() -> subprocess.Popen:
    """Spin off the Flask dashboard as a detached child process."""
    proc = subprocess.Popen(
        [sys.executable, str(REPO_ROOT / "scripts" / "serve_results.py")],
        cwd=REPO_ROOT,
    )
    time.sleep(3)  # give Flask a moment to bind before the run floods stdout
    print(
        f"Dashboard: {DASHBOARD_URL} (pid {proc.pid}) — refresh the page as "
        "steps complete. It keeps running after this script exits; stop it "
        "by killing the process listening on port 5000."
    )
    return proc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Full pipeline run: dashboard, backtests, coverage, "
        "validation battery.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Force fresh price data from IB Gateway (default: parquet cache).",
    )
    parser.add_argument(
        "--spa",
        action="store_true",
        help="Also run the library-wide SPA / Reality Check after the battery.",
    )
    parser.add_argument(
        "--reports",
        action="store_true",
        help="Also regenerate static md/html reports for every strategy.",
    )
    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Do not spin off the dashboard server.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    py = sys.executable
    results: list = []

    if not args.no_dashboard:
        _start_dashboard()

    backtest_cmd = [py, "scripts/run_backtest.py", "--all", "--use-definitions"]
    if args.refresh:
        backtest_cmd.append("--refresh")
    results.append(
        ("backtests", _run_step("Load data + backtest all", backtest_cmd, fatal=True))
    )

    results.append(
        (
            "coverage",
            _run_step(
                "Mechanism coverage",
                [py, "scripts/tag_mechanisms.py", "--coverage"],
                fatal=False,
            ),
        )
    )

    results.append(
        (
            "validation",
            _run_step(
                "Validation battery (all strategies)",
                [py, "scripts/validate_strategy.py", "--all"],
                fatal=False,
            ),
        )
    )

    if args.spa:
        results.append(
            (
                "spa",
                _run_step(
                    "SPA / Reality Check (library-wide)",
                    [py, "scripts/run_all_overfitting.py", "--spa"],
                    fatal=False,
                ),
            )
        )

    if args.reports:
        results.append(
            (
                "reports",
                _run_step(
                    "Static reports",
                    [py, "scripts/generate_report.py", "--all", "--format", "both"],
                    fatal=False,
                ),
            )
        )

    print(f"\n{'=' * 70}\nFULL RUN COMPLETE\n{'=' * 70}")
    for name, ok in results:
        print(f"  {name.ljust(12)} {'OK' if ok else 'FAILED'}")
    if not args.no_dashboard:
        print(f"\nDashboard still serving at {DASHBOARD_URL}")


if __name__ == "__main__":
    main()
