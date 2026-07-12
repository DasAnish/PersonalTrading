#!/usr/bin/env python3
"""
Idempotent one-command pipeline: sync repo, refresh data, gate, analyse.

Kills the state-divergence failure class (unpulled origin/main, stale cache
silently truncating panels, half-overwritten results, drifted index) by
running everything in one order and writing a manifest saying exactly what
happened. Safe to run any time — nightly via Task Scheduler, or by hand when
sitting down to work. Every step degrades loudly, never silently:

    1. git    fetch origin; refuse on dirty tree; fast-forward when behind
              (never merges a divergent branch)
    2. data   scripts/refresh_data.py — IB Gateway down is tolerated: the
              run continues on the existing cache, stamped data_refreshed=false
    3. gate   scripts/validate_cache.py — content sanity + freshness gate;
              a failed gate ABORTS analysis (override with --force)
    4. run    scripts/run_full_analysis.py (backtest + validate + SPA)
    5. index  scripts/rebuild_index.py — index rebuilt from disk truth
    6. archive strategies_index.json + per-strategy small JSONs to
              results/runs/<run_id>/ for run-over-run diffing

Writes results/run_manifest.json (and a copy in the run archive) with run id,
git state, per-symbol data end dates, step outcomes, and failures. The
dashboard and session-start checks read this instead of trusting memory.

Never touches IB order endpoints — market data and local files only.

Usage:
    python scripts/run_nightly.py                  # full pipeline
    python scripts/run_nightly.py --fast           # --fast analysis (skip PBO)
    python scripts/run_nightly.py --skip-refresh   # offline: cache as-is
    python scripts/run_nightly.py --force          # run analysis despite gate
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backtesting.results_schema import (  # noqa: E402
    INDEX_FILE,
    OVERFITTING_FILE,
    VALIDATION_FILE,
)

logger = logging.getLogger(__name__)

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
RESULTS_DIR = REPO_ROOT / "results"
RUNS_DIR = RESULTS_DIR / "runs"
MANIFEST_PATH = RESULTS_DIR / "run_manifest.json"

# Per-strategy files small enough to archive every run (metrics + verdicts,
# not the fat portfolio_history/transactions payloads).
ARCHIVE_STRATEGY_FILES = (
    "metrics.json",
    "info.json",
    VALIDATION_FILE,
    OVERFITTING_FILE,
)

EXIT_GATEWAY_DOWN = 2  # matches scripts/refresh_data.py


def _git(*args: str) -> tuple[int, str]:
    """Run a git command at the repo root; return (exit_code, stdout)."""
    proc = subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    return proc.returncode, (proc.stdout or "").strip()


def _run_step(manifest: dict, name: str, cmd: list[str]) -> int:
    """Run one subprocess step, recording outcome + timing in the manifest."""
    logger.info("=" * 70)
    logger.info(f"[{name}] {' '.join(cmd)}")
    start = time.time()
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT))
    elapsed = round(time.time() - start, 1)
    manifest["steps"][name] = {"exit_code": proc.returncode, "seconds": elapsed}
    level = logging.INFO if proc.returncode == 0 else logging.ERROR
    logger.log(level, f"[{name}] exit {proc.returncode} in {elapsed}s")
    return proc.returncode


def sync_git(manifest: dict) -> bool:
    """
    Fetch origin and fast-forward main when safely possible.

    Refuses (returns False) only on a dirty working tree — running analysis
    on uncommitted state produces results no commit can reproduce. A
    diverged branch is recorded but not merged; the run continues on local
    state.
    """
    git_info: dict = {"synced": False, "dirty": False, "diverged": False}
    manifest["git"] = git_info

    code, _ = _git("fetch", "origin")
    git_info["fetched"] = code == 0
    if code != 0:
        logger.warning("git fetch failed (offline?) — continuing on local state")

    # Untracked files are tolerated (git aborts a fast-forward itself on a
    # collision); modified tracked files are not — analysis on uncommitted
    # code produces results no commit can reproduce.
    _, porcelain = _git("status", "--porcelain", "--untracked-files=no")
    if porcelain:
        git_info["dirty"] = True
        logger.error(
            "Working tree has uncommitted changes to tracked files — "
            "refusing to run the pipeline on state no commit can reproduce. "
            "Commit/stash first, or pass --skip-git."
        )
        return False

    _, counts = _git("rev-list", "--left-right", "--count", "HEAD...origin/main")
    if counts:
        ahead, behind = (int(x) for x in counts.split())
        git_info["ahead"] = ahead
        git_info["behind"] = behind
        if behind and not ahead:
            code, _ = _git("merge", "--ff-only", "origin/main")
            git_info["synced"] = code == 0
            if code == 0:
                logger.info(f"Fast-forwarded main by {behind} commit(s)")
            else:
                logger.warning("Fast-forward failed — continuing on local state")
        elif behind and ahead:
            git_info["diverged"] = True
            logger.warning(
                f"Branch diverged from origin/main ({ahead} ahead / {behind} "
                "behind) — NOT merging; reconcile manually."
            )
        else:
            git_info["synced"] = True

    _, head = _git("rev-parse", "HEAD")
    git_info["head"] = head
    return True


def archive_run(manifest: dict, run_id: str) -> None:
    """Copy the index + per-strategy small JSONs to results/runs/<run_id>/."""
    run_dir = RUNS_DIR / run_id
    strategies_out = run_dir / "strategies"
    strategies_out.mkdir(parents=True, exist_ok=True)

    index_path = RESULTS_DIR / INDEX_FILE
    copied = 0
    if index_path.exists():
        shutil.copy2(index_path, run_dir / INDEX_FILE)

    strategies_dir = RESULTS_DIR / "strategies"
    if strategies_dir.is_dir():
        for strategy_dir in strategies_dir.iterdir():
            if not strategy_dir.is_dir():
                continue
            target = strategies_out / strategy_dir.name
            for filename in ARCHIVE_STRATEGY_FILES:
                src = strategy_dir / filename
                if src.exists():
                    target.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, target / filename)
            copied += 1

    manifest["archive"] = {
        "run_dir": str(run_dir.relative_to(REPO_ROOT).as_posix()),
        "strategies_archived": copied,
    }
    logger.info(f"Archived index + {copied} strategy result sets to {run_dir}")


def write_manifest(manifest: dict, run_id: str) -> None:
    """Write the manifest to results/ and into the run archive."""
    manifest["finished_at"] = datetime.now().isoformat()
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, indent=2) + "\n"
    MANIFEST_PATH.write_text(payload, encoding="utf-8")
    run_dir = RUNS_DIR / run_id
    if run_dir.is_dir():
        (run_dir / "manifest.json").write_text(payload, encoding="utf-8")
    logger.info(f"Manifest -> {MANIFEST_PATH}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="One-command nightly pipeline: sync, refresh, gate, analyse.",
    )
    parser.add_argument("--skip-git", action="store_true", help="Skip git sync.")
    parser.add_argument(
        "--skip-refresh", action="store_true", help="Skip the IB data refresh."
    )
    parser.add_argument(
        "--skip-analysis",
        action="store_true",
        help="Stop after the data steps (refresh + validate + gate).",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Pass --fast to run_full_analysis.py (skips PBO sweeps).",
    )
    parser.add_argument(
        "--max-stale-days",
        type=int,
        default=7,
        help="Freshness gate threshold in days (default 7).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run analysis even when the freshness gate fails.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    py = sys.executable

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    manifest: dict = {
        "run_id": run_id,
        "started_at": datetime.now().isoformat(),
        "args": vars(args),
        "steps": {},
        "data_refreshed": False,
        "gate_failed": None,
        "ok": False,
    }

    try:
        # 1. git sync
        if not args.skip_git:
            if not sync_git(manifest):
                return 1

        # 2. data refresh — gateway down is a tolerated, recorded outcome
        if not args.skip_refresh:
            code = _run_step(
                manifest, "refresh", [py, str(SCRIPTS_DIR / "refresh_data.py")]
            )
            if code == 0:
                manifest["data_refreshed"] = True
            elif code == EXIT_GATEWAY_DOWN:
                logger.warning(
                    "IB Gateway down — continuing on existing cache "
                    "(manifest stamped data_refreshed=false)"
                )
            else:
                logger.error("Data refresh errored — continuing on existing cache")
            refresh_report = RESULTS_DIR / "data_refresh.json"
            if manifest["data_refreshed"] and refresh_report.exists():
                try:
                    report = json.loads(refresh_report.read_text(encoding="utf-8"))
                    manifest["data_end_dates"] = {
                        s: e.get("data_end") for s, e in report["symbols"].items()
                    }
                except Exception as exc:
                    logger.warning(f"Could not read refresh report: {exc}")

        # 2b. NAV snapshot — soft step, only worth trying if the gateway
        # answered the refresh (calendar time can't be backfilled, so grab
        # the reading whenever one is available).
        if manifest["data_refreshed"]:
            _run_step(
                manifest, "snapshot_nav", [py, str(SCRIPTS_DIR / "snapshot_nav.py")]
            )

        # 3. cache sanity + freshness gate
        code = _run_step(
            manifest,
            "validate_cache",
            [
                py,
                str(SCRIPTS_DIR / "validate_cache.py"),
                "--max-stale-days",
                str(args.max_stale_days),
            ],
        )
        manifest["gate_failed"] = code != 0
        validation_report = RESULTS_DIR / "cache_validation.json"
        if validation_report.exists():
            try:
                report = json.loads(validation_report.read_text(encoding="utf-8"))
                manifest["panel_end"] = report.get("panel_end")
                manifest["stale_symbols"] = report.get("stale", [])
                manifest["missing_symbols"] = report.get("missing", [])
            except Exception as exc:
                logger.warning(f"Could not read cache validation report: {exc}")
        if manifest["gate_failed"] and not args.force:
            logger.error(
                "Freshness gate failed — NOT running analysis on rotten data. "
                "Fix the cache or pass --force to override."
            )
            return 1
        if manifest["gate_failed"] and args.force:
            logger.warning("Gate failed but --force given — analysis will run.")

        if args.skip_analysis:
            manifest["ok"] = not manifest["gate_failed"]
            return 0 if manifest["ok"] else 1

        # 4. full analysis
        analysis_cmd = [py, str(SCRIPTS_DIR / "run_full_analysis.py")]
        if args.fast:
            analysis_cmd.append("--fast")
        if _run_step(manifest, "analysis", analysis_cmd) != 0:
            logger.error("Analysis failed — index NOT rebuilt, results untouched.")
            return 1

        # 5. rebuild index from disk truth
        if (
            _run_step(
                manifest, "rebuild_index", [py, str(SCRIPTS_DIR / "rebuild_index.py")]
            )
            != 0
        ):
            return 1
        index_path = RESULTS_DIR / INDEX_FILE
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
            manifest["total_strategies"] = index.get("total_strategies")
            manifest["results_vintage"] = index.get("vintage")
            manifest["results_metrics_schema"] = index.get("metrics_schema")
            if (index.get("vintage") or {}).get("mixed"):
                logger.warning(
                    "Rebuilt index reports MIXED result vintages — some "
                    "strategies were not re-run against the current panel."
                )
            if (index.get("metrics_schema") or {}).get("mixed"):
                logger.warning(
                    "Rebuilt index reports MIXED metrics schema versions — some "
                    "strategies were built with different annualization logic."
                )
        except Exception as exc:
            logger.warning(f"Could not read rebuilt index: {exc}")

        # 6. archive for run-over-run diffing
        archive_run(manifest, run_id)

        manifest["ok"] = True
        logger.info("=" * 70)
        logger.info(
            f"Nightly run {run_id} complete: "
            f"{manifest.get('total_strategies', '?')} strategies, "
            f"panel ends {manifest.get('panel_end', '?')}, "
            f"data_refreshed={manifest['data_refreshed']}"
        )
        return 0
    finally:
        write_manifest(manifest, run_id)


if __name__ == "__main__":
    sys.exit(main())
