"""
Snapshot current IB positions to results/live_positions.json.

This is the *producer* for the live-risk page's offline cache: run it while IB
Gateway is connected and it writes a positions snapshot that the dashboard's
/live-risk tab falls back to when IB is later offline.

Read-only with respect to the account — it fetches positions and writes a local
JSON file. It NEVER places, modifies, or cancels any order.

Usage:
    python scripts/snapshot_positions.py
    python scripts/snapshot_positions.py --out results/live_positions.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ib_wrapper.client import IBClient  # noqa: E402

DEFAULT_OUT = Path("results") / "live_positions.json"


async def _fetch_positions() -> list:
    client = IBClient()
    await client.connect()
    try:
        raw = await client.get_positions()
    finally:
        client.disconnect()  # synchronous — do not await
    return [
        {
            "symbol": p.symbol,
            "shares": float(p.position),
            "price": float(p.market_price),
            "value": float(p.market_value),
        }
        for p in raw
        if p.position
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Snapshot IB positions to a JSON cache for the live-risk page.",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=str(DEFAULT_OUT),
        help=f"Output path (default: {DEFAULT_OUT}).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="Seconds to wait for the IB fetch (default: 15).",
    )
    args = parser.parse_args()

    try:
        positions = asyncio.run(
            asyncio.wait_for(_fetch_positions(), timeout=args.timeout)
        )
    except Exception as exc:
        print(f"ERROR: could not fetch positions from IB: {exc}")
        print("Is IB Gateway running and connected on the configured port?")
        sys.exit(1)

    import pandas as pd

    snapshot = {
        "as_of": pd.Timestamp.utcnow().isoformat(),
        "positions": positions,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)
        f.write("\n")

    total = sum(p["value"] for p in positions)
    print(f"Wrote {len(positions)} positions (total value {total:,.2f}) to {out_path}")


if __name__ == "__main__":
    main()
