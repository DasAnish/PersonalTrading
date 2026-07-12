#!/usr/bin/env python3
"""
Extend ETF history back past inception by splicing a long-history proxy.

The binding constraint on the whole validation stack is calendar time:
SPA is blocked because T is too short, and no asset-direction holdout fixes
a time-direction shortage. This tool buys decades by stitching each UCITS
ETF onto a long-lived proxy (mostly US listings of the same index) declared
in strategy_definitions/proxy_map.json.

Safety valve for wrong mappings: before splicing, the proxy's daily-return
correlation with the real ETF over their overlap must clear ``--min-corr``
(default 0.85) with at least ``--min-overlap`` shared days — a bad proxy
fails loudly instead of silently polluting the extended cache.

Splice construction (scale-join):
    - factor = ETF close / proxy close on the first shared date
    - proxy rows strictly before the ETF's start, price columns scaled by
      the factor, then the real ETF series verbatim
    - written to data/cache_extended/<symbol>_<start>_<end>.parquet using
      the normal cache filename scheme, so
      ``HistoricalDataCache("data/cache_extended")`` just works

Caveat (also in proxy_map.json): proxies mostly quote in USD; pre-inception
returns are proxy-currency returns. Good for regime / relative research and
long-T validation, NOT for precise GBP return levels.

Raw proxy downloads are cached in data/cache_proxies/ so re-splicing after a
mapping tweak needs no IB round-trip. IB Gateway down: symbols whose proxy
is already cached still splice; the rest are reported and skipped.

Usage:
    python scripts/extend_history.py                 # all mapped symbols
    python scripts/extend_history.py --symbols VUSA,SGLN --min-corr 0.9
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from data import HistoricalDataCache, EXPECTED_WHAT_TO_SHOW  # noqa: E402
from ib_wrapper.client import IBClient  # noqa: E402
from ib_wrapper.config import Config  # noqa: E402

logger = logging.getLogger(__name__)

PROXY_MAP_PATH = Path("strategy_definitions") / "proxy_map.json"
PROXY_CACHE_DIR = "data/cache_proxies"
EXTENDED_CACHE_DIR = "data/cache_extended"
DEFAULT_OUT = Path("results") / "extend_history.json"

PROXY_YEARS = 25
PRICE_COLUMNS = ("open", "high", "low", "close", "average")


def load_proxy_map(path: Path = PROXY_MAP_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)["proxies"]
    return {sym: spec for sym, spec in raw.items() if spec}


async def fetch_proxy(
    client_holder: dict, spec: dict, cache: HistoricalDataCache
) -> pd.DataFrame:
    """Proxy series from the proxy cache, fetching via IB on a miss."""
    end = datetime.now() - timedelta(days=1)
    start = end - timedelta(days=365 * PROXY_YEARS)
    cached = cache.load_cached_data(
        spec["symbol"], start, end, max_age_days=30, tolerance_days=30
    )
    if not cached.empty:
        return cached

    if client_holder.get("unavailable"):
        return pd.DataFrame()
    if client_holder.get("client") is None:
        try:
            client = IBClient(Config())
            await client.connect()
            client_holder["client"] = client
        except Exception as exc:
            logger.warning(f"IB Gateway unreachable ({exc}) — cached proxies only")
            client_holder["unavailable"] = True
            return pd.DataFrame()

    client = client_holder["client"]
    df = await client.market_data.download_extended_history(
        symbol=spec["symbol"],
        start_date=start,
        end_date=end,
        bar_size="1 day",
        what_to_show=EXPECTED_WHAT_TO_SHOW,
        sec_type=spec.get("sec_type", "STK"),
        exchange=spec.get("exchange", "SMART"),
        currency=spec.get("currency", "USD"),
    )
    if not df.empty:
        cache.save_cached_data(
            spec["symbol"], df, start, end, what_to_show=EXPECTED_WHAT_TO_SHOW
        )
    return df


def splice(
    etf: pd.DataFrame, proxy: pd.DataFrame, min_overlap: int, min_corr: float
) -> tuple[pd.DataFrame | None, dict]:
    """Scale-join proxy onto the ETF. Returns (extended df | None, stats)."""
    overlap = etf.index.intersection(proxy.index)
    stats: dict = {"overlap_days": len(overlap), "correlation": None}
    if len(overlap) < min_overlap:
        stats["error"] = f"only {len(overlap)} overlap days (< {min_overlap})"
        return None, stats

    etf_r = etf.loc[overlap, "close"].pct_change().dropna()
    proxy_r = proxy.loc[overlap, "close"].pct_change().dropna()
    corr = float(etf_r.corr(proxy_r))
    stats["correlation"] = round(corr, 4)
    if not corr >= min_corr:  # also catches NaN
        stats["error"] = f"overlap correlation {corr:.3f} < {min_corr} — bad proxy?"
        return None, stats

    # Scale by the median ETF/proxy close ratio over the early overlap —
    # a single-day ratio would let one bad print at the join distort every
    # pre-history level.
    join_window = overlap[: min(20, len(overlap))]
    ratios = etf.loc[join_window, "close"].astype(float) / proxy.loc[
        join_window, "close"
    ].astype(float)
    factor = float(ratios.median())
    pre = proxy.loc[proxy.index < etf.index[0]].copy()
    if pre.empty:
        stats["error"] = "proxy adds no history before the ETF's start"
        return None, stats
    for col in PRICE_COLUMNS:
        if col in pre.columns:
            pre[col] = pre[col] * factor

    extended = pd.concat([pre, etf])
    extended = extended[~extended.index.duplicated(keep="last")].sort_index()
    stats.update(
        etf_start=etf.index[0].date().isoformat(),
        extended_start=extended.index[0].date().isoformat(),
        years_gained=round((etf.index[0] - extended.index[0]).days / 365.25, 1),
        rows=len(extended),
    )
    return extended, stats


async def run(symbols: list[str], min_overlap: int, min_corr: float) -> dict:
    proxy_map = load_proxy_map()
    etf_cache = HistoricalDataCache()
    proxy_cache = HistoricalDataCache(PROXY_CACHE_DIR)
    extended_cache = HistoricalDataCache(EXTENDED_CACHE_DIR)
    client_holder: dict = {"client": None, "unavailable": False}

    report: dict = {"as_of": datetime.now().isoformat(), "symbols": {}}
    try:
        for symbol in symbols:
            spec = proxy_map.get(symbol)
            if spec is None:
                report["symbols"][symbol] = {"status": "no_proxy_mapping"}
                continue
            entry: dict = {"status": "failed", "proxy": spec["symbol"]}
            report["symbols"][symbol] = entry

            etf = etf_cache.load_best_cached_data(symbol)
            if etf.empty:
                entry["error"] = "no cached ETF data — run refresh_data.py first"
                continue
            proxy = await fetch_proxy(client_holder, spec, proxy_cache)
            if proxy.empty:
                entry["error"] = "proxy data unavailable (IB down, not cached)"
                continue

            extended, stats = splice(etf, proxy, min_overlap, min_corr)
            entry.update(stats)
            if extended is None:
                logger.warning(f"✗ {symbol}: {stats.get('error')}")
                continue

            extended_cache.save_cached_data(
                symbol,
                extended,
                extended.index[0].to_pydatetime(),
                extended.index[-1].to_pydatetime(),
                what_to_show=EXPECTED_WHAT_TO_SHOW,
            )
            entry["status"] = "ok"
            logger.info(
                f"✓ {symbol}: +{stats['years_gained']}y via {spec['symbol']} "
                f"(corr {stats['correlation']}, {stats['rows']} rows)"
            )
    finally:
        if client_holder.get("client") is not None:
            client_holder["client"].disconnect()  # synchronous — do not await

    ok = sum(1 for e in report["symbols"].values() if e.get("status") == "ok")
    report["ok_count"] = ok
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Splice long-history proxies onto cached ETF series.",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma-separated subset (default: every mapped symbol).",
    )
    parser.add_argument(
        "--min-corr",
        type=float,
        default=0.85,
        help="Minimum overlap daily-return correlation to accept (0.85).",
    )
    parser.add_argument(
        "--min-overlap",
        type=int,
        default=250,
        help="Minimum shared trading days for the correlation check (250).",
    )
    parser.add_argument("--out", type=str, default=str(DEFAULT_OUT))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    proxy_map = load_proxy_map()
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = sorted(proxy_map)

    report = asyncio.run(run(symbols, args.min_overlap, args.min_corr))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")

    logger.info(f"Extended {report['ok_count']}/{len(symbols)} symbols -> {out_path}")
    return 0 if report["ok_count"] else 1


if __name__ == "__main__":
    sys.exit(main())
