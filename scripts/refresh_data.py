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

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from data import (  # noqa: E402
    HistoricalDataCache,
    EXPECTED_WHAT_TO_SHOW,
    latest_cache_file,
)
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

# Incremental refresh parameters
OVERLAP_MIN_DAYS = 20
OVERLAP_TOL = 1e-4


async def _try_incremental_fetch(
    client,
    symbol: str,
    spec: dict,
    cache: HistoricalDataCache,
) -> tuple[pd.DataFrame, str] | None:
    """Try incremental 1-year fetch with overlap verification.

    Returns:
        (DataFrame, what_to_show) if successful, None if overlap mismatch detected
        (triggering a full refetch).
    """
    # Check if we have a cached file to extend
    result = latest_cache_file(symbol)
    if result is None:
        return None  # No cache to extend

    old_path, old_df = result
    if old_df.empty or "close" not in old_df.columns:
        return None

    # Fetch 1 year ending now
    try:
        df_1y = await client.market_data.download_extended_history(
            symbol=symbol,
            start_date=END_DATE - pd.Timedelta(days=365),
            end_date=END_DATE,
            bar_size=BAR_SIZE,
            what_to_show=EXPECTED_WHAT_TO_SHOW,
            sec_type=spec["sec_type"],
            exchange=spec["exchange"],
            currency=spec["currency"],
        )
    except Exception:
        return None  # Can't fetch 1 year; will do full refetch

    if df_1y.empty:
        return None

    # Find overlap
    old_dates = set(old_df.index.date)
    new_dates = set(df_1y.index.date)
    overlap_dates = sorted(old_dates & new_dates)

    if len(overlap_dates) < OVERLAP_MIN_DAYS:
        # Not enough overlap; do full refetch
        logger.debug(
            f"{symbol}: overlap too short ({len(overlap_dates)} < {OVERLAP_MIN_DAYS})"
        )
        return None

    # Check for adjustments: max(abs(new_close/old_close - 1)) over overlap
    overlap_start = overlap_dates[0]
    overlap_end = overlap_dates[-1]
    old_overlap = old_df[
        (old_df.index.date >= overlap_start) & (old_df.index.date <= overlap_end)
    ]
    new_overlap = df_1y[
        (df_1y.index.date >= overlap_start) & (df_1y.index.date <= overlap_end)
    ]

    if len(old_overlap) == 0 or len(new_overlap) == 0:
        return None

    # Align on close prices
    old_close = old_overlap["close"].values
    new_close = new_overlap["close"].values

    if len(old_close) != len(new_close):
        # Date mismatch; do full refetch
        return None

    # Check tolerance
    ratio_error = (new_close / old_close) - 1.0
    max_error = max(abs(ratio_error))

    if max_error > OVERLAP_TOL:
        # Adjustment detected; log and do full refetch
        logger.info(
            f"adjustment detected for {symbol}, max error={max_error:.2e}, full refetch"
        )
        return None

    # Overlap verified; concat cached + new, dedup (keep new)
    # old_df up to (but not including) overlap_start, then all of df_1y
    pre_overlap = old_df[old_df.index.date < overlap_start]
    combined = pd.concat([pre_overlap, df_1y])
    combined = combined[~combined.index.duplicated(keep="last")]
    combined = combined.sort_index()

    return (combined, EXPECTED_WHAT_TO_SHOW)


async def refresh_symbols(
    symbols: list[str], connect_timeout: float, use_full: bool = False
) -> dict:
    """
    Connect to IB once and refresh the cache for every symbol.

    Returns the report dict. Raises ConnectionError if the initial connect
    fails (mapped to exit code 2 by main()).

    Args:
        symbols: List of symbols to refresh
        connect_timeout: Timeout in seconds for IB connection
        use_full: If True, force full-history fetch for all symbols
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
            entry: dict = {
                "status": "failed",
                "rows": 0,
                "data_end": None,
                "what_to_show": None,
                "refresh_mode": None,
            }
            try:
                # Decide on refresh strategy
                if use_full:
                    refresh_mode = "full"
                else:
                    # Try incremental
                    result = await _try_incremental_fetch(client, symbol, spec, cache)
                    if result is not None:
                        df, what_to_show = result
                        # Save incremental result
                        cache.save_cached_data(
                            symbol,
                            df,
                            df.index[0].to_pydatetime(),
                            df.index[-1].to_pydatetime(),
                            what_to_show=what_to_show,
                        )
                        # Delete old file (find it and remove)
                        old_result = latest_cache_file(symbol)
                        if old_result and old_result[0] != cache._get_cache_path(
                            symbol,
                            df.index[0].to_pydatetime(),
                            df.index[-1].to_pydatetime(),
                        ):
                            try:
                                old_result[0].unlink()
                                logger.debug(
                                    f"Deleted old cache file: {old_result[0].name}"
                                )
                            except Exception as e:
                                logger.warning(
                                    f"Failed to delete old cache file {old_result[0].name}: {e}"
                                )
                        entry.update(
                            status="ok",
                            rows=len(df),
                            data_end=df.index[-1].date().isoformat(),
                            what_to_show=what_to_show,
                            refresh_mode="incremental",
                        )
                        logger.info(
                            f"✓ {symbol}: {len(df)} rows (incremental), "
                            f"ends {entry['data_end']}"
                        )
                        report["symbols"][symbol] = entry
                        continue

                    refresh_mode = "full"

                # Full-history fetch
                what_to_show = EXPECTED_WHAT_TO_SHOW
                df = await client.market_data.download_extended_history(
                    symbol=symbol,
                    start_date=START_DATE,
                    end_date=END_DATE,
                    bar_size=BAR_SIZE,
                    what_to_show=what_to_show,
                    sec_type=spec["sec_type"],
                    exchange=spec["exchange"],
                    currency=spec["currency"],
                )
                if df.empty:
                    entry["error"] = "empty dataframe returned"
                    logger.warning(f"✗ {symbol}: empty dataframe")
                else:
                    # Delete old file before saving new one
                    old_result = latest_cache_file(symbol)
                    if old_result:
                        try:
                            old_result[0].unlink()
                            logger.debug(
                                f"Deleted old cache file: {old_result[0].name}"
                            )
                        except Exception as e:
                            logger.warning(
                                f"Failed to delete old cache file {old_result[0].name}: {e}"
                            )

                    cache.save_cached_data(
                        symbol,
                        df,
                        df.index[0].to_pydatetime(),
                        df.index[-1].to_pydatetime(),
                        what_to_show=what_to_show,
                    )
                    entry.update(
                        status="ok",
                        rows=len(df),
                        data_end=df.index[-1].date().isoformat(),
                        what_to_show=what_to_show,
                        refresh_mode=(
                            refresh_mode
                            if refresh_mode == "full"
                            else "full_after_adjustment"
                        ),
                    )
                    logger.info(
                        f"✓ {symbol}: {len(df)} rows ({entry['refresh_mode']}), "
                        f"ends {entry['data_end']} (what_to_show={what_to_show})"
                    )
            except Exception as exc:
                # Per-symbol fallback: some LSE/IBIS ETFs reject ADJUSTED_LAST
                # IB error 162 = Unknown error, 321 = Client parameter validation failed
                exc_str = str(exc)
                if any(err in exc_str for err in ["162", "321", "ADJUSTED_LAST"]):
                    logger.warning(
                        f"✗ {symbol}: ADJUSTED_LAST failed ({exc}), "
                        f"retrying with TRADES fallback"
                    )
                    try:
                        what_to_show = "TRADES"
                        df = await client.market_data.download_extended_history(
                            symbol=symbol,
                            start_date=START_DATE,
                            end_date=END_DATE,
                            bar_size=BAR_SIZE,
                            what_to_show=what_to_show,
                            sec_type=spec["sec_type"],
                            exchange=spec["exchange"],
                            currency=spec["currency"],
                        )
                        if not df.empty:
                            cache.save_cached_data(
                                symbol,
                                df,
                                df.index[0].to_pydatetime(),
                                df.index[-1].to_pydatetime(),
                                what_to_show=what_to_show,
                            )
                            entry.update(
                                status="ok",
                                rows=len(df),
                                data_end=df.index[-1].date().isoformat(),
                                what_to_show=what_to_show,
                                refresh_mode="full",
                            )
                            logger.info(
                                f"✓ {symbol}: {len(df)} rows via TRADES fallback, "
                                f"ends {entry['data_end']}"
                            )
                        else:
                            entry["error"] = "empty dataframe (TRADES fallback)"
                            logger.warning(
                                f"✗ {symbol}: TRADES fallback returned empty"
                            )
                    except Exception as fallback_exc:
                        entry["error"] = f"TRADES fallback failed: {fallback_exc}"
                        logger.error(
                            f"✗ {symbol}: TRADES fallback failed: {fallback_exc}"
                        )
                else:
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
    parser.add_argument(
        "--full",
        action="store_true",
        help="Force full-history fetch for all symbols (skips incremental refresh).",
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
        report = asyncio.run(
            refresh_symbols(symbols, args.connect_timeout, use_full=args.full)
        )
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
