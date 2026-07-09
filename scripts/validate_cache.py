#!/usr/bin/env python3
"""
Sanity-check the parquet data cache and enforce a hard freshness gate.

Freshness ≠ correctness: a cache file's name says nothing about what is
inside it. This script opens the newest cache file per asset and checks the
actual contents:

    - file exists, is readable, is non-empty
    - date index is strictly increasing with no duplicates
    - close prices present and positive
    - NaN fraction in close below threshold
    - no absurd single-day returns (fat-finger / bad-splice detector)
    - no long calendar gaps
    - data end date fresh enough (the AIGC failure mode: one stale symbol
      silently truncating every aligned backtest panel)

Writes results/cache_validation.json and exits non-zero when the gate fails,
so callers (scripts/run_nightly.py, pre-run hooks) can refuse to run analysis
on rotten data instead of producing silently-truncated results.

Exit codes:
    0  all checks passed (warnings allowed)
    1  gate failed: missing/corrupt symbol, or panel end older than
       --max-stale-days

Usage:
    python scripts/validate_cache.py
    python scripts/validate_cache.py --max-stale-days 7
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from data.cache import HistoricalDataCache, _CACHE_FILENAME_RE  # noqa: E402

from backtest_lib.config import SYMBOLS  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_OUT = Path("results") / "cache_validation.json"

MAX_ABS_DAILY_RETURN = 0.35  # warn above this — bad splice / unit change
MAX_GAP_BUSINESS_DAYS = 10  # warn above this — hole in the series
MAX_NAN_FRACTION = 0.02  # warn above this — patchy data


def _newest_cache_file(cache_dir: Path, symbol: str) -> Path | None:
    """Newest cache file for symbol by parsed filename end date, else None."""
    best: tuple[datetime, Path] | None = None
    for path in cache_dir.glob(f"{symbol}_*.parquet"):
        match = _CACHE_FILENAME_RE.match(path.name)
        if not match:
            continue
        try:
            end = datetime.strptime(match.group("end"), "%Y%m%d")
        except ValueError:
            continue
        if best is None or end > best[0]:
            best = (end, path)
    return best[1] if best else None


def check_symbol(cache_dir: Path, symbol: str, max_stale_days: int) -> dict:
    """Run all content checks for one symbol. Returns a report entry."""
    entry: dict = {
        "status": "ok",
        "file": None,
        "rows": 0,
        "data_start": None,
        "data_end": None,
        "stale_days": None,
        "errors": [],
        "warnings": [],
    }

    path = _newest_cache_file(cache_dir, symbol)
    if path is None:
        entry["status"] = "missing"
        entry["errors"].append("no cache file")
        return entry
    entry["file"] = path.name

    try:
        df = pd.read_parquet(path)
    except Exception as exc:
        entry["status"] = "corrupt"
        entry["errors"].append(f"unreadable parquet: {exc}")
        return entry
    if df.empty:
        entry["status"] = "corrupt"
        entry["errors"].append("empty dataframe")
        return entry

    entry["rows"] = len(df)
    idx = pd.DatetimeIndex(df.index)
    entry["data_start"] = idx[0].date().isoformat()
    entry["data_end"] = idx[-1].date().isoformat()
    entry["stale_days"] = (datetime.now() - idx[-1].to_pydatetime()).days

    if idx.has_duplicates:
        entry["errors"].append(f"{idx.duplicated().sum()} duplicate dates")
    if not idx.is_monotonic_increasing:
        entry["errors"].append("date index not sorted")

    if "close" not in df.columns:
        entry["errors"].append(f"no close column (have: {list(df.columns)})")
    else:
        close = df["close"]
        nan_frac = float(close.isna().mean())
        if nan_frac > MAX_NAN_FRACTION:
            entry["warnings"].append(f"close NaN fraction {nan_frac:.1%}")
        valid = close.dropna()
        if (valid <= 0).any():
            entry["errors"].append(f"{int((valid <= 0).sum())} non-positive closes")
        returns = valid.pct_change().abs()
        worst = float(returns.max()) if len(returns) else 0.0
        if worst > MAX_ABS_DAILY_RETURN:
            worst_day = returns.idxmax()
            entry["warnings"].append(
                f"daily move {worst:.0%} on {pd.Timestamp(worst_day).date()}"
                " — possible bad splice / unit change"
            )

    if len(idx) > 1:
        gaps = pd.Series(idx).diff().dt.days.fillna(0)
        max_gap = int(gaps.max())
        if max_gap > MAX_GAP_BUSINESS_DAYS:
            gap_at = idx[int(gaps.idxmax())].date()
            entry["warnings"].append(f"{max_gap}-day gap ending {gap_at}")

    if entry["stale_days"] is not None and entry["stale_days"] > max_stale_days:
        entry["status"] = "stale"
        entry["warnings"].append(
            f"data ends {entry['data_end']} ({entry['stale_days']} days behind)"
        )

    if entry["errors"]:
        entry["status"] = "corrupt"
    return entry


def validate(max_stale_days: int, cache_dir: str = "data/cache") -> dict:
    """Validate every asset's cache. Returns the full report with verdict."""
    cache = HistoricalDataCache(cache_dir)
    symbols_report = {
        symbol: check_symbol(cache.cache_dir, symbol, max_stale_days)
        for symbol in SYMBOLS
    }

    end_dates = [
        e["data_end"] for e in symbols_report.values() if e["data_end"] is not None
    ]
    panel_end = min(end_dates) if end_dates else None
    panel_stale_days = (
        (datetime.now() - datetime.fromisoformat(panel_end)).days if panel_end else None
    )

    missing = [s for s, e in symbols_report.items() if e["status"] == "missing"]
    corrupt = [s for s, e in symbols_report.items() if e["status"] == "corrupt"]
    stale = [s for s, e in symbols_report.items() if e["status"] == "stale"]

    gate_failed = bool(missing or corrupt) or (
        panel_stale_days is not None and panel_stale_days > max_stale_days
    )

    return {
        "as_of": datetime.now().isoformat(),
        "max_stale_days": max_stale_days,
        "panel_end": panel_end,
        "panel_stale_days": panel_stale_days,
        "missing": missing,
        "corrupt": corrupt,
        "stale": stale,
        "gate_failed": gate_failed,
        "symbols": symbols_report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sanity-check the data cache and enforce a freshness gate.",
    )
    parser.add_argument(
        "--max-stale-days",
        type=int,
        default=7,
        help="Gate fails when the aligned panel end is older than this (default 7).",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=str(DEFAULT_OUT),
        help=f"Report path (default: {DEFAULT_OUT}).",
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        default="data/cache",
        help="Cache directory (default: data/cache).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    report = validate(args.max_stale_days, args.cache_dir)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")

    for symbol, entry in report["symbols"].items():
        for problem in entry["errors"]:
            logger.error(f"{symbol}: {problem}")
        for warning in entry["warnings"]:
            logger.warning(f"{symbol}: {warning}")

    logger.info(
        f"Panel ends {report['panel_end']} "
        f"({report['panel_stale_days']} days behind); "
        f"{len(report['missing'])} missing, {len(report['corrupt'])} corrupt, "
        f"{len(report['stale'])} stale -> {out_path}"
    )
    if report["gate_failed"]:
        logger.error(
            "FRESHNESS GATE FAILED — refusing is the point: fix the cache "
            "(run scripts/refresh_data.py with IB Gateway up) before analysis."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
