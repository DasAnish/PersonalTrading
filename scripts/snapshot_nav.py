#!/usr/bin/env python3
"""
Record a daily account NAV + positions snapshot for live-vs-backtest tracking.

Out-of-sample calendar time cannot be backfilled: every day without a
recorded NAV is a day of live evidence lost forever. This script appends one
row per calendar day to ``live_tracking/nav_history.csv`` and writes the full
positions detail to ``live_tracking/positions/<date>.json``. Re-running on
the same day overwrites that day's row (idempotent), so it is safe to hook
into scripts/run_nightly.py or Task Scheduler and also run by hand.

Optionally records a named strategy's current target weights (from its
latest backtest ``weights_history.json``) alongside the positions, so
implementation shortfall can later be computed from the same file.

Read-only with respect to the account — it fetches NAV/positions and writes
local files. It NEVER places, modifies, or cancels any order.

Usage:
    python scripts/snapshot_nav.py
    python scripts/snapshot_nav.py --strategy hrp_15vol
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backtesting.results_schema import STRATEGY_FILES, strategy_dir  # noqa: E402
from ib_wrapper.client import IBClient  # noqa: E402

logger = logging.getLogger(__name__)

TRACKING_DIR = Path("live_tracking")
NAV_CSV = TRACKING_DIR / "nav_history.csv"
POSITIONS_DIR = TRACKING_DIR / "positions"

NAV_FIELDS = [
    "date",
    "recorded_at",
    "net_liquidation",
    "total_cash",
    "gross_position_value",
    "n_positions",
]


async def fetch_snapshot() -> tuple[dict, list[dict]]:
    """Fetch account summary + positions from IB (single connection)."""
    client = IBClient()
    await client.connect()
    try:
        summary = await client.get_account_summary(
            tags=["NetLiquidation", "TotalCashValue", "GrossPositionValue"]
        )
        raw = await client.get_positions()
    finally:
        client.disconnect()  # synchronous — do not await
    positions = [
        {
            "symbol": p.symbol,
            "shares": float(p.position),
            "price": float(p.market_price),
            "value": float(p.market_value),
        }
        for p in raw
        if p.position
    ]
    return summary, positions


def load_target_weights(strategy_key: str) -> dict | None:
    """Latest target weights row from the strategy's backtest results."""
    path = (
        strategy_dir(Path("results"), strategy_key) / STRATEGY_FILES["weights_history"]
    )
    if not path.exists():
        logger.warning(f"No weights_history for '{strategy_key}' at {path}")
        return None
    try:
        with open(path, "r") as f:
            rows = json.load(f)
    except Exception as exc:
        logger.warning(f"Unreadable weights_history for '{strategy_key}': {exc}")
        return None
    if not rows:
        return None
    last = dict(rows[-1])
    as_of = last.pop("date", None)
    weights = {k: v for k, v in last.items() if isinstance(v, (int, float))}
    return {"strategy": strategy_key, "as_of": as_of, "weights": weights}


def upsert_nav_row(row: dict) -> None:
    """Append today's row to nav_history.csv, replacing any same-day row."""
    rows: list[dict] = []
    if NAV_CSV.exists():
        with open(NAV_CSV, "r", newline="", encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r.get("date") != row["date"]]
    rows.append({k: str(row[k]) for k in NAV_FIELDS})
    rows.sort(key=lambda r: r["date"])
    NAV_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(NAV_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=NAV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record daily account NAV + positions for live tracking.",
    )
    parser.add_argument(
        "--strategy",
        type=str,
        default=None,
        help="Also record this strategy's latest target weights.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Seconds to wait for the IB fetch (default: 30).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        summary, positions = asyncio.run(
            asyncio.wait_for(fetch_snapshot(), timeout=args.timeout)
        )
    except Exception as exc:
        logger.error(f"Could not fetch account snapshot from IB: {exc}")
        logger.error("Is IB Gateway running and connected on the configured port?")
        return 1

    today = date.today().isoformat()
    nav_row = {
        "date": today,
        "recorded_at": datetime.now().isoformat(),
        "net_liquidation": summary.get("NetLiquidation"),
        "total_cash": summary.get("TotalCashValue"),
        "gross_position_value": summary.get("GrossPositionValue"),
        "n_positions": len(positions),
    }
    upsert_nav_row(nav_row)

    detail = {
        "date": today,
        "recorded_at": nav_row["recorded_at"],
        "account_summary": summary,
        "positions": positions,
    }
    if args.strategy:
        detail["target"] = load_target_weights(args.strategy)

    POSITIONS_DIR.mkdir(parents=True, exist_ok=True)
    detail_path = POSITIONS_DIR / f"{today}.json"
    with open(detail_path, "w", encoding="utf-8") as f:
        json.dump(detail, f, indent=2)
        f.write("\n")

    logger.info(
        f"NAV {nav_row['net_liquidation']} recorded for {today} "
        f"({len(positions)} positions) -> {NAV_CSV} + {detail_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
