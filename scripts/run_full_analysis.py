#!/usr/bin/env python3
"""
One-shot "analyse everything" entry point.

Runs the full library-wide pipeline in order:

  1. Backtest every strategy definition          (scripts/run_backtest.py --all)
  2. Per-strategy validation battery             (scripts/validate_strategy.py --all)
     (MinBTL, DSR, CPCV, block bootstrap -> validation.json per strategy)
  3. Library-wide overfitting + SPA / Reality Check
         (scripts/run_all_overfitting.py --spa --walk-forward --composed-pbo)
     (DSR/k-fold per strategy, PBO sweeps + walk-forward per base family,
      group PBO for composed/overlay families, SPA across the library)

Step 3 is the one that corrects for having *tried many strategies* — the
per-strategy battery in step 2 only judges each strategy in isolation, whereas
the SPA / White's Reality Check in step 3 judges the whole family for
data-snooping and writes results/spa_analysis.json.

Usage:
  python scripts/run_full_analysis.py                 # backtest -> validate -> overfitting+SPA
  python scripts/run_full_analysis.py --skip-backtest # reuse existing results/
  python scripts/run_full_analysis.py --fast          # pass --skip-pbo to the overfitting step
  python scripts/run_full_analysis.py --skip-validate # SPA/overfitting only

Exit code is non-zero if any executed step fails.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent


def _run(label: str, cmd: list[str]) -> float:
    """Run one step, streaming its output. Returns elapsed seconds; raises on failure."""
    print("\n" + "=" * 70)
    print(f"[{label}] {' '.join(cmd)}")
    print("=" * 70, flush=True)
    start = time.time()
    result = subprocess.run(cmd, cwd=str(REPO_ROOT))
    elapsed = time.time() - start
    if result.returncode != 0:
        raise SystemExit(
            f"[{label}] FAILED (exit {result.returncode}) after {elapsed:.1f}s"
        )
    print(f"[{label}] done in {elapsed:.1f}s", flush=True)
    return elapsed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backtest + validate + overfitting/SPA for the whole library.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
        "--fast",
        action="store_true",
        help=(
            "Pass --skip-pbo to the overfitting step (DSR/k-fold + SPA only; "
            "skips PBO sweeps, walk-forward, and composed PBO)."
        ),
    )
    args = parser.parse_args()

    py = sys.executable
    steps: list[tuple[str, list[str]]] = []

    if not args.skip_backtest:
        steps.append(
            ("1/3 backtest", [py, str(SCRIPTS_DIR / "run_backtest.py"), "--all"])
        )
    if not args.skip_validate:
        steps.append(
            ("2/3 validate", [py, str(SCRIPTS_DIR / "validate_strategy.py"), "--all"])
        )
    if not args.skip_overfitting:
        overfit_cmd = [py, str(SCRIPTS_DIR / "run_all_overfitting.py"), "--spa"]
        if args.fast:
            overfit_cmd.append("--skip-pbo")
        else:
            # Opt-in flags in run_all_overfitting.py; the full pipeline wants
            # the complete suite (PBO sweeps + walk-forward + composed PBO).
            overfit_cmd += ["--walk-forward", "--composed-pbo"]
        steps.append(("3/3 overfitting+SPA", overfit_cmd))

    if not steps:
        print("Nothing to do — all steps skipped.")
        return

    overall_start = time.time()
    for label, cmd in steps:
        _run(label, cmd)

    print("\n" + "=" * 70)
    print(f"Full analysis complete in {time.time() - overall_start:.1f}s.")
    print("  Per-strategy battery : results/strategies/<key>/validation.json")
    print("  Library-wide SPA     : results/spa_analysis.json")
    print("  Dashboard            : /validation  (python scripts/serve_results.py)")
    print("=" * 70)


if __name__ == "__main__":
    main()
