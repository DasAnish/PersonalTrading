#!/usr/bin/env python3
"""
Sanity check for ADJUSTED_LAST cache migration.

Compares old TRADES cache against new ADJUSTED_LAST cache to verify migration
correctness: last close prices match (within tolerance), implied dividend yield
is reasonable for distributing ETFs.

Exit codes:
    0  migration passed (all symbols within tolerance)
    1  migration failed (some symbol close differs >0.5% or other error)
    2  missing cache directory or other fatal error

Usage:
    python scripts/check_adjusted_migration.py \\
        --old data/cache_trades_backup \\
        --new data/cache \\
        --json-out results/adjusted_migration.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from data import HistoricalDataCache  # noqa: E402

logger = logging.getLogger(__name__)


def _read_newest_raw(cache_dir: Path, symbol: str) -> pd.DataFrame:
    """Read the newest ``{symbol}_*.parquet`` directly, bypassing the cache's
    what_to_show stamp gate.

    The old TRADES cache is unstamped (or TRADES-stamped), so the normal loader
    treats it as a cache miss. For migration comparison we want the raw frame
    regardless of stamp. Returns an empty DataFrame if nothing matches.
    """
    matches = list(cache_dir.glob(f"{symbol}_*.parquet"))
    if not matches:
        return pd.DataFrame()
    # newest by end-date encoded as the last filename segment
    newest = max(matches, key=lambda f: f.stem.split("_")[-1])
    df = pd.read_parquet(newest)
    if not isinstance(df.index, pd.DatetimeIndex):
        for col in ("date", "Date", "datetime"):
            if col in df.columns:
                df = df.set_index(pd.DatetimeIndex(df[col]))
                break
    return df


TOLERANCE_CLOSE_PCT = 0.005  # 0.5% tolerance on last close
MIN_YIELD_PA = -0.01  # -1%/yr (allow negative for losing positions)
MAX_YIELD_PA = 0.06  # 6%/yr (reasonable for distributing ETFs)


def compare_caches(old_dir: str, new_dir: str) -> list[dict]:
    """Compare old and new cache files per symbol.

    Compute alignment metrics on overlapping dates:
    - close_ratio_last: new close / old close on latest shared date
    - total_return_old/new: CAGR over shared period
    - implied_div_yield_pa: new CAGR - old CAGR (dividend impact)

    Args:
        old_dir: Path to old TRADES cache
        new_dir: Path to new ADJUSTED_LAST cache

    Returns:
        List of dicts (one per symbol) with metrics and flag if problematic
    """
    new_cache = HistoricalDataCache(new_dir)

    old_path = Path(old_dir)
    new_path = Path(new_dir)

    results = []

    # Find all symbols in old cache
    symbols = set()
    for f in old_path.glob("*_*.parquet"):
        # Match filename pattern {symbol}_{start}_{end}.parquet
        parts = f.stem.split("_")
        if len(parts) >= 3:
            # Last two parts are yyyymmdd dates
            try:
                int(parts[-1])  # end date
                int(parts[-2])  # start date
                # Symbol is everything before dates
                symbol = "_".join(parts[:-2])
                symbols.add(symbol)
            except ValueError:
                pass

    logger.info(f"Found {len(symbols)} symbols in old cache")

    for symbol in sorted(symbols):
        entry = {"symbol": symbol, "status": "failed"}
        try:
            # Old cache is TRADES-stamped/unstamped -> read raw (the stamp gate
            # would otherwise reject it as a miss). New cache is ADJUSTED_LAST.
            old_df = _read_newest_raw(old_path, symbol)
            new_df = new_cache.load_best_cached_data(symbol)

            if old_df.empty or new_df.empty:
                entry["error"] = (
                    f"missing data (old empty: {old_df.empty}, new empty: {new_df.empty})"
                )
                results.append(entry)
                continue

            # Align on common dates
            old_close = (
                old_df["close"] if "close" in old_df.columns else old_df.iloc[:, 0]
            )
            new_close = (
                new_df["close"] if "close" in new_df.columns else new_df.iloc[:, 0]
            )

            # Find overlap
            overlap_dates = old_close.index.intersection(new_close.index)
            if len(overlap_dates) < 20:
                entry["error"] = f"insufficient overlap: {len(overlap_dates)} days"
                results.append(entry)
                continue

            # Compare last close (most recent shared date)
            last_shared = overlap_dates[-1]
            old_last = float(old_close[last_shared])
            new_last = float(new_close[last_shared])

            if old_last <= 0:
                entry["error"] = f"invalid old close: {old_last}"
                results.append(entry)
                continue

            close_ratio_last = new_last / old_last
            entry["close_ratio_last"] = round(close_ratio_last, 6)
            entry["close_diff_pct"] = round((close_ratio_last - 1.0) * 100, 4)

            # Flag if >0.5% diff
            if abs(close_ratio_last - 1.0) > TOLERANCE_CLOSE_PCT:
                entry["error"] = (
                    f"last close differs {entry['close_diff_pct']:.2f}% (> 0.5% tolerance)"
                )
                results.append(entry)
                continue

            # CAGR over overlap period
            overlap_start = overlap_dates[0]
            overlap_end = overlap_dates[-1]
            n_years = (overlap_end - overlap_start).days / 365.25

            old_start_price = float(old_close[overlap_start])
            new_start_price = float(new_close[overlap_start])

            if old_start_price <= 0 or new_start_price <= 0:
                entry["error"] = "invalid start close"
                results.append(entry)
                continue

            if n_years < 0.1:
                entry["error"] = "overlap too short for CAGR"
                results.append(entry)
                continue

            old_cagr = (old_last / old_start_price) ** (1.0 / n_years) - 1.0
            new_cagr = (new_last / new_start_price) ** (1.0 / n_years) - 1.0

            entry["total_return_old"] = round(
                (old_last / old_start_price - 1.0) * 100, 2
            )
            entry["total_return_new"] = round(
                (new_last / new_start_price - 1.0) * 100, 2
            )
            entry["cagr_old"] = round(old_cagr * 100, 2)
            entry["cagr_new"] = round(new_cagr * 100, 2)

            # Implied dividend yield
            implied_div_yield_pa = new_cagr - old_cagr
            entry["implied_div_yield_pa"] = round(implied_div_yield_pa * 100, 2)

            # Flag unreasonable yields
            if (
                implied_div_yield_pa < MIN_YIELD_PA
                or implied_div_yield_pa > MAX_YIELD_PA
            ):
                entry["error"] = (
                    f"implied yield {entry['implied_div_yield_pa']:.2f}% out of range "
                    f"({MIN_YIELD_PA*100:.1f}%-{MAX_YIELD_PA*100:.1f}%)"
                )
                results.append(entry)
                continue

            entry["status"] = "ok"
            entry["overlap_days"] = len(overlap_dates)
            logger.info(
                f"✓ {symbol}: close ratio {close_ratio_last:.6f}, "
                f"implied yield {implied_div_yield_pa * 100:.2f}%"
            )

        except Exception as e:
            entry["error"] = str(e)
            logger.error(f"✗ {symbol}: {e}")

        results.append(entry)

    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sanity check ADJUSTED_LAST cache migration vs old TRADES cache.",
    )
    parser.add_argument(
        "--old",
        type=str,
        required=True,
        help="Path to old TRADES cache (e.g., data/cache_trades_backup)",
    )
    parser.add_argument(
        "--new",
        type=str,
        required=True,
        help="Path to new ADJUSTED_LAST cache (e.g., data/cache)",
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default="results/adjusted_migration.json",
        help="Path to write JSON report (default: results/adjusted_migration.json)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    # Verify directories exist
    old_path = Path(args.old)
    new_path = Path(args.new)

    if not old_path.exists():
        logger.error(f"Old cache directory not found: {old_path}")
        return 2
    if not new_path.exists():
        logger.error(f"New cache directory not found: {new_path}")
        return 2

    logger.info(f"Comparing old cache ({args.old}) vs new cache ({args.new})")

    # Run comparison
    results = compare_caches(args.old, args.new)

    # Write report
    report = {
        "as_of": datetime.now().isoformat(),
        "old_cache": args.old,
        "new_cache": args.new,
        "symbols": results,
        "summary": {
            "total": len(results),
            "ok": sum(1 for r in results if r["status"] == "ok"),
            "failed": sum(1 for r in results if r["status"] == "failed"),
        },
    }

    out_path = Path(args.json_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")

    logger.info(f"Report written to {out_path}")
    logger.info(
        f"Summary: {report['summary']['ok']}/{report['summary']['total']} symbols OK"
    )

    # Exit non-zero if any close differs >0.5%
    has_close_failures = any("close differs" in r.get("error", "") for r in results)
    if has_close_failures:
        logger.error("Migration FAILED: some last closes differ >0.5%")
        return 1

    # Exit non-zero if any failed
    if report["summary"]["failed"] > 0:
        logger.error(f"Migration FAILED: {report['summary']['failed']} symbols failed")
        return 1

    logger.info("Migration PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
