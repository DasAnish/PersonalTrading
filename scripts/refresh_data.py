#!/usr/bin/env python3
"""
Refresh the parquet data cache for every asset while IB Gateway is up.

Standalone data-refresh step for the nightly pipeline (scripts/run_nightly.py):
connects to IB once, downloads the full history window for every symbol in
strategy_definitions/assets/, saves each to data/cache/, and writes a
per-symbol report to results/data_refresh.json.

Read-only with respect to the account — market data only. It NEVER places,
modifies, or cancels any order.

Exit codes:
    0  refresh ran (individual symbols may still have failed — see report)
    2  IB Gateway unreachable — cache untouched, caller should proceed on
       existing cache and mark the run's data as stale
    1  unexpected error

Usage:
    python scripts/refresh_data.py
    python scripts/refresh_data.py --symbols VUSA,SGLN --out results/data_refresh.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from data import HistoricalDataCache  # noqa: E402
from ib_wrapper.client import IBClient  # noqa: E402
from ib_wrapper.config import Config  # noqa: E402

from backtest_lib.config import (  # noqa: E402
    BAR_SIZE,
    END_DATE,
    START_DATE,
    SYMBOL_SPECS,
    SYMBOLS,
)

logger = logging.getLogger(__name__)

DEFAULT_OUT = Path("results") / "data_refresh.json"
EXIT_GATEWAY_DOWN = 2


async def refresh_symbols(symbols: list[str], connect_timeout: float) -> dict:
    """
    Connect to IB once and refresh the cache for every symbol.

    Returns the report dict. Raises ConnectionError if the initial connect
    fails (mapped to exit code 2 by main()).
    """
    cache = HistoricalDataCache()
    client = IBClient(Config())
    try:
        await asyncio.wait_for(client.connect(), timeout=connect_timeout)
    except Exception as exc:
        raise ConnectionError(f"IB Gateway unreachable: {exc}") from exc

    report: dict = {
        "as_of": datetime.now().isoformat(),
        "start_date": START_DATE.date().isoformat(),
        "end_date": END_DATE.date().isoformat(),
        "symbols": {},
    }
    try:
        for symbol in symbols:
            spec = SYMBOL_SPECS[symbol]
            entry: dict = {"status": "failed", "rows": 0, "data_end": None}
            try:
                df = await client.market_data.download_extended_history(
                    symbol=symbol,
                    start_date=START_DATE,
                    end_date=END_DATE,
                    bar_size=BAR_SIZE,
                    sec_type=spec["sec_type"],
                    exchange=spec["exchange"],
                    currency=spec["currency"],
                )
                if df.empty:
                    entry["error"] = "empty dataframe returned"
                    logger.warning(f"✗ {symbol}: empty dataframe")
                else:
                    # Name the cache file by the data actually received —
                    # a filename claiming the requested END_DATE when IB
                    # returned less is exactly the staleness lie the
                    # validator exists to catch.
                    cache.save_cached_data(
                        symbol,
                        df,
                        df.index[0].to_pydatetime(),
                        df.index[-1].to_pydatetime(),
                    )
                    entry.update(
                        status="ok",
                        rows=len(df),
                        data_end=df.index[-1].date().isoformat(),
                    )
                    logger.info(f"✓ {symbol}: {len(df)} rows, ends {entry['data_end']}")
            except Exception as exc:
                entry["error"] = str(exc)
                logger.error(f"✗ {symbol}: {exc}")
            report["symbols"][symbol] = entry
    finally:
        client.disconnect()  # synchronous — do not await

    ok = sum(1 for e in report["symbols"].values() if e["status"] == "ok")
    report["ok_count"] = ok
    report["failed_count"] = len(report["symbols"]) - ok
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh the parquet cache for all assets from IB Gateway.",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma-separated subset (default: every asset definition).",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=str(DEFAULT_OUT),
        help=f"Report path (default: {DEFAULT_OUT}).",
    )
    parser.add_argument(
        "--connect-timeout",
        type=float,
        default=20.0,
        help="Seconds to wait for the IB connection (default: 20).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
        unknown = [s for s in symbols if s not in SYMBOL_SPECS]
        if unknown:
            logger.error(f"Unknown symbols (no asset definition): {unknown}")
            return 1
    else:
        symbols = list(SYMBOLS)

    try:
        report = asyncio.run(refresh_symbols(symbols, args.connect_timeout))
    except ConnectionError as exc:
        logger.warning(f"{exc} — cache left untouched.")
        return EXIT_GATEWAY_DOWN
    except Exception as exc:
        logger.error(f"Refresh failed: {exc}")
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")

    logger.info(
        f"Refreshed {report['ok_count']}/{len(report['symbols'])} symbols "
        f"-> {out_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
