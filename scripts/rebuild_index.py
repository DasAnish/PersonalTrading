#!/usr/bin/env python3
"""
Rebuild results/strategies_index.json from what is actually on disk.

The index normally accretes via per-strategy merges in
``backtesting.results_io.save_strategy_results``; after crashes, partial
--all runs, or manual deletions it drifts from ``results/strategies/``.
This script makes the directory tree the source of truth: every strategy
directory containing a valid ``metrics.json`` + ``info.json`` gets an index
entry, and nothing else does.

Each entry also gets a ``config_hash`` — sha256 of the strategy's definition
file under ``strategy_definitions/`` — so run-over-run diffs can tell "the
data moved" apart from "the strategy changed" (a Sharpe delta is only a
regression when the config hash is unchanged).

Usage:
    python scripts/rebuild_index.py
    python scripts/rebuild_index.py --results-dir results --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backtesting.results_schema import (  # noqa: E402
    INDEX_FILE,
    METRICS_SCHEMA_VERSION,
    STRATEGY_FILES,
)

logger = logging.getLogger(__name__)

DEFINITION_SUBDIRS = ("allocations", "composed", "overlays", "portfolios")
STRATEGY_DEFS_DIR = Path("strategy_definitions")


def definition_hash(
    strategy_key: str, defs_dir: Path = STRATEGY_DEFS_DIR
) -> str | None:
    """sha256 of the strategy's definition file content, or None if not found."""
    for sub in DEFINITION_SUBDIRS:
        for ext in (".json", ".yaml"):
            path = defs_dir / sub / f"{strategy_key}{ext}"
            if path.exists():
                return hashlib.sha256(path.read_bytes()).hexdigest()
    return None


def rebuild(results_dir: Path) -> dict:
    """Build a fresh index dict from results/strategies/*/ contents."""
    strategies_dir = results_dir / "strategies"
    index_path = results_dir / INDEX_FILE

    # Preserve the run config block — it describes how backtests were run
    # (capital, costs, rebalance frequency) and is not derivable from the
    # per-strategy files.
    config: dict = {}
    if index_path.exists():
        try:
            with open(index_path, "r") as f:
                config = json.load(f).get("config", {})
        except Exception as exc:
            logger.warning(f"Could not read existing index config: {exc}")

    entries: dict = {}
    skipped: list[str] = []
    for strategy_dir in sorted(p for p in strategies_dir.iterdir() if p.is_dir()):
        key = strategy_dir.name
        try:
            with open(strategy_dir / STRATEGY_FILES["metrics"], "r") as f:
                metrics = json.load(f)
            with open(strategy_dir / STRATEGY_FILES["info"], "r") as f:
                info = json.load(f)
        except FileNotFoundError:
            skipped.append(key)
            continue
        except Exception as exc:
            logger.warning(f"Skipping {key}: unreadable results ({exc})")
            skipped.append(key)
            continue
        entries[key] = {
            "path": str((strategy_dir.relative_to(results_dir)).as_posix()),
            "metrics": metrics,
            "info": info,
            "config_hash": definition_hash(key),
            "data_end": metrics.get("data_end"),
        }

    # Vintage summary: results from different data windows are not
    # comparable (the mixed-vintage failure mode — half the library rebuilt
    # against a truncated panel). Surface it here so the dashboard and the
    # nightly manifest can warn instead of someone diffing lengths by hand.
    end_dates = sorted({e["data_end"] for e in entries.values() if e["data_end"]})
    vintage = {
        "min_data_end": end_dates[0] if end_dates else None,
        "max_data_end": end_dates[-1] if end_dates else None,
        "mixed": len(end_dates) > 1,
        "distinct_data_ends": len(end_dates),
    }

    # Metrics schema version summary: detect when strategies were built with
    # different metrics schema versions (e.g., pre-stamp vs stamped). This
    # indicates strategies built in different runs and not directly comparable.
    versions = sorted(
        {e["metrics"].get("metrics_version", 1) for e in entries.values()}
    )
    metrics_schema = {
        "current": METRICS_SCHEMA_VERSION,
        "versions_present": versions,
        "mixed": len(versions) > 1,
    }

    return {
        "strategies": entries,
        "config": config,
        "run_date": datetime.now().isoformat(),
        "total_strategies": len(entries),
        "rebuilt": True,
        "skipped": skipped,
        "vintage": vintage,
        "metrics_schema": metrics_schema,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild strategies_index.json from results/strategies/.",
    )
    parser.add_argument(
        "--results-dir",
        type=str,
        default="results",
        help="Top-level results directory (default: results).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the summary without writing the index.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    results_dir = Path(args.results_dir)
    if not (results_dir / "strategies").is_dir():
        logger.error(f"No strategies directory under {results_dir}")
        return 1

    index = rebuild(results_dir)

    if index["skipped"]:
        logger.warning(
            f"Skipped {len(index['skipped'])} dirs without valid results: "
            f"{index['skipped']}"
        )
    missing_hash = [k for k, e in index["strategies"].items() if not e["config_hash"]]
    if missing_hash:
        logger.warning(f"No definition file found for: {missing_hash}")
    if index["vintage"]["mixed"]:
        logger.warning(
            "MIXED VINTAGES: strategy data ends span "
            f"{index['vintage']['min_data_end']} .. "
            f"{index['vintage']['max_data_end']} "
            f"({index['vintage']['distinct_data_ends']} distinct) — "
            "cross-strategy comparisons are unreliable until a full re-run."
        )
    if index["metrics_schema"]["mixed"]:
        logger.warning(
            "MIXED METRICS SCHEMA: strategy metrics versions span "
            f"{index['metrics_schema']['versions_present']} — "
            "strategies built at different times with different annualization logic. "
            "Cross-strategy comparisons are unreliable until a full re-run."
        )

    if args.dry_run:
        logger.info(f"[dry-run] would index {index['total_strategies']} strategies")
        return 0

    index_path = results_dir / INDEX_FILE
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)
    logger.info(f"Wrote {index_path} ({index['total_strategies']} strategies)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
