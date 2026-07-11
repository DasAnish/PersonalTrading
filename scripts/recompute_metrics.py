#!/usr/bin/env python3
"""
Regenerate every strategy's metrics.json from its saved portfolio history.

Fixes the stored fallout of the annualization bug (metrics.json used to
annualize monthly rebalance-period returns with sqrt(252), inflating
Sharpe/volatility ~4.6x) without re-running any backtests: the portfolio
histories on disk are fine, only the derived numbers were wrong.

All numbers come from ``analytics.metrics.summarize_performance`` — the
same canonical implementation the backtest writer now uses — so metrics,
validation, and dashboard can no longer disagree on annualization. Fields
the writer owns but this script can't derive (final_value, transaction
counts) are preserved from the existing file.

Run ``scripts/rebuild_index.py`` afterwards so the index picks up the
corrected numbers (run_nightly.py does both).

Usage:
    python scripts/recompute_metrics.py
    python scripts/recompute_metrics.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analytics.metrics import summarize_performance  # noqa: E402
from backtesting.results_schema import (  # noqa: E402
    STRATEGY_FILES,
    load_portfolio_values,
)

logger = logging.getLogger(__name__)

PRESERVED_FIELDS = ("final_value", "total_transactions", "rebalances")


def recompute(results_dir: Path, dry_run: bool) -> dict:
    strategies_dir = results_dir / "strategies"
    counts = {"updated": 0, "unchanged": 0, "skipped": 0}

    for strategy_dir in sorted(p for p in strategies_dir.iterdir() if p.is_dir()):
        key = strategy_dir.name
        metrics_path = strategy_dir / STRATEGY_FILES["metrics"]
        if not metrics_path.exists():
            counts["skipped"] += 1
            continue

        values = load_portfolio_values(results_dir, key)
        if len(values) < 2:
            logger.warning(f"skip {key}: portfolio history too short")
            counts["skipped"] += 1
            continue

        try:
            with open(metrics_path, "r") as f:
                old = json.load(f)
        except Exception as exc:
            logger.warning(f"skip {key}: unreadable metrics.json ({exc})")
            counts["skipped"] += 1
            continue

        new = summarize_performance(values)
        for field in PRESERVED_FIELDS:
            if field in old:
                new[field] = old[field]

        old_sharpe = old.get("sharpe_ratio")
        if old_sharpe is not None and new["sharpe_ratio"] is not None:
            drift = abs(old_sharpe - new["sharpe_ratio"])
            if drift < 1e-9:
                counts["unchanged"] += 1
                continue
            logger.info(
                f"{key}: sharpe {old_sharpe:.3f} -> {new['sharpe_ratio']:.3f} "
                f"(ppy {new['periods_per_year']}, ends {new['data_end']})"
            )

        if not dry_run:
            with open(metrics_path, "w") as f:
                json.dump(new, f, indent=2)
        counts["updated"] += 1

    return counts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recompute metrics.json for every strategy from disk.",
    )
    parser.add_argument("--results-dir", type=str, default="results")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    results_dir = Path(args.results_dir)
    if not (results_dir / "strategies").is_dir():
        logger.error(f"No strategies directory under {results_dir}")
        return 1

    counts = recompute(results_dir, args.dry_run)
    prefix = "[dry-run] would update" if args.dry_run else "Updated"
    logger.info(
        f"{prefix} {counts['updated']} metrics files "
        f"({counts['unchanged']} already correct, {counts['skipped']} skipped). "
        "Now run: python scripts/rebuild_index.py"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
