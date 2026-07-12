"""Virtual per-strategy allocation ledger (pure, no IB imports).

Records the trades the user executed **manually** in IB, per strategy, so each
strategy runs as a virtual sub-portfolio ("slice") whose size floats with its
own performance. The store is append-only; holdings and cash are always DERIVED
from the event log, never stored directly. Slice NAV is always shares x market
closes — never the stored fill prices.

Store: ``live_tracking/strategy_ledger.json`` (gitignored)::

    {"schema_version": 1, "events": [
      {"id": "a1b2c3d4e5f6", "recorded_at": "2026-07-12T18:30:00",
       "trade_date": "2026-07-12", "strategy": "hrp_15vol",
       "external_cash_delta": 1000.0,
       "fills": [{"symbol": "VUSA", "shares_delta": 8.0, "price": 95.23,
                  "commission": 3.0}],
       "note": "initial funding + first buy"}]}

Semantics (ISA — no tax fields; all prices GBP base, FX folded into price):
  * ``external_cash_delta`` = cash moved personal<->slice (+ = funding).
  * A fill's cash impact = ``-(shares_delta * price) - commission``.
  * Slice cash = sum of both across the strategy's events.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd

LEDGER_PATH = Path("live_tracking") / "strategy_ledger.json"
LEDGER_SCHEMA_VERSION = 1

_SHARE_EPS = 1e-9


# ---------------------------------------------------------------------------
# Store I/O
# ---------------------------------------------------------------------------
def _empty_ledger() -> dict:
    return {"schema_version": LEDGER_SCHEMA_VERSION, "events": []}


def load_ledger(path: Path = LEDGER_PATH) -> dict:
    """Load the ledger, returning an empty skeleton if the file is absent."""
    path = Path(path)
    if not path.exists():
        return _empty_ledger()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("schema_version", LEDGER_SCHEMA_VERSION)
    data.setdefault("events", [])
    return data


def _validate_event(event: dict) -> None:
    strategy = event.get("strategy")
    if not isinstance(strategy, str) or not strategy.strip():
        raise ValueError("event.strategy must be a non-empty string")

    trade_date = event.get("trade_date")
    try:
        datetime.fromisoformat(str(trade_date))
    except (TypeError, ValueError):
        raise ValueError(f"event.trade_date must be ISO date, got {trade_date!r}")

    fills = event.get("fills", []) or []
    if not isinstance(fills, list):
        raise ValueError("event.fills must be a list")
    for fill in fills:
        if not isinstance(fill, dict):
            raise ValueError("each fill must be an object")
        if not isinstance(fill.get("symbol"), str) or not fill["symbol"]:
            raise ValueError("fill.symbol must be a non-empty string")
        try:
            float(fill["shares_delta"])
            price = float(fill["price"])
            float(fill.get("commission", 0.0))
        except (KeyError, TypeError, ValueError):
            raise ValueError("fill needs numeric shares_delta, price, commission")
        if price <= 0:
            raise ValueError(f"fill.price must be > 0, got {price}")

    external = float(event.get("external_cash_delta", 0.0) or 0.0)
    if not fills and external == 0.0:
        raise ValueError("event must have non-empty fills or external_cash_delta != 0")


def append_event(event: dict, path: Path = LEDGER_PATH) -> dict:
    """Validate ``event``, stamp id/recorded_at, append, and atomically write."""
    _validate_event(event)
    stored = dict(event)
    stored.setdefault("external_cash_delta", 0.0)
    stored.setdefault("fills", [])
    stored.setdefault("note", "")
    stored["id"] = uuid.uuid4().hex[:12]
    stored["recorded_at"] = datetime.now().isoformat(timespec="seconds")

    path = Path(path)
    ledger = load_ledger(path)
    ledger["events"].append(stored)

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(ledger, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    return stored


# ---------------------------------------------------------------------------
# Derived holdings / cash
# ---------------------------------------------------------------------------
def holdings_by_strategy(ledger: dict) -> Dict[str, Dict[str, float]]:
    """Net shares per (strategy, symbol); positions with |shares| < 1e-9 dropped."""
    out: Dict[str, Dict[str, float]] = {}
    for event in ledger.get("events", []):
        strat = event["strategy"]
        book = out.setdefault(strat, {})
        for fill in event.get("fills", []) or []:
            book[fill["symbol"]] = book.get(fill["symbol"], 0.0) + float(
                fill["shares_delta"]
            )
    for strat in list(out):
        out[strat] = {
            sym: sh for sym, sh in out[strat].items() if abs(sh) >= _SHARE_EPS
        }
    return out


def cash_by_strategy(ledger: dict) -> Dict[str, float]:
    """Slice cash per strategy = sum of external_cash_delta and fill cash impacts."""
    out: Dict[str, float] = {}
    for event in ledger.get("events", []):
        strat = event["strategy"]
        cash = out.get(strat, 0.0)
        cash += float(event.get("external_cash_delta", 0.0) or 0.0)
        for fill in event.get("fills", []) or []:
            cash += -(float(fill["shares_delta"]) * float(fill["price"])) - float(
                fill.get("commission", 0.0)
            )
        out[strat] = cash
    return out


def personal_holdings(ib_positions: Dict[str, float], ledger: dict) -> Dict[str, float]:
    """IB shares minus the sum of all strategy-claimed shares, floored at 0."""
    claimed: Dict[str, float] = {}
    for book in holdings_by_strategy(ledger).values():
        for sym, sh in book.items():
            claimed[sym] = claimed.get(sym, 0.0) + sh
    out: Dict[str, float] = {}
    for sym, ib_sh in ib_positions.items():
        residual = float(ib_sh) - claimed.get(sym, 0.0)
        out[sym] = residual if residual > _SHARE_EPS else 0.0
    return out


def slice_value(holdings: Dict[str, float], prices: Dict[str, float]) -> float:
    """Mark-to-market value of a holdings book at the given (base) prices."""
    total = 0.0
    for sym, sh in holdings.items():
        price = prices.get(sym)
        if price is not None:
            total += float(sh) * float(price)
    return total


def reconcile(ib_positions: Dict[str, float], ledger: dict) -> List[dict]:
    """Rows where the ledger claims more shares of a symbol than IB actually holds."""
    claimed: Dict[str, float] = {}
    for book in holdings_by_strategy(ledger).values():
        for sym, sh in book.items():
            claimed[sym] = claimed.get(sym, 0.0) + sh
    rows: List[dict] = []
    for sym, claimed_sh in claimed.items():
        ib_sh = float(ib_positions.get(sym, 0.0))
        if claimed_sh > ib_sh + 1e-6:
            rows.append(
                {"symbol": sym, "ledger_shares": claimed_sh, "ib_shares": ib_sh}
            )
    return rows


# ---------------------------------------------------------------------------
# Time series (slice holdings + NAV)
# ---------------------------------------------------------------------------
def slice_holdings_series(ledger: dict, strategy: str) -> pd.DataFrame:
    """Date-indexed cumulative shares per symbol for one strategy's fills."""
    deltas: Dict[pd.Timestamp, Dict[str, float]] = {}
    for event in ledger.get("events", []):
        if event["strategy"] != strategy:
            continue
        date = pd.Timestamp(event["trade_date"])
        row = deltas.setdefault(date, {})
        for fill in event.get("fills", []) or []:
            row[fill["symbol"]] = row.get(fill["symbol"], 0.0) + float(
                fill["shares_delta"]
            )
    if not deltas:
        return pd.DataFrame()
    delta_df = pd.DataFrame(deltas).T.fillna(0.0).sort_index()
    return delta_df.cumsum()


def _slice_cash_series(ledger: dict, strategy: str) -> pd.Series:
    """Date-indexed cumulative slice cash for one strategy."""
    per_date: Dict[pd.Timestamp, float] = {}
    for event in ledger.get("events", []):
        if event["strategy"] != strategy:
            continue
        date = pd.Timestamp(event["trade_date"])
        cash = float(event.get("external_cash_delta", 0.0) or 0.0)
        for fill in event.get("fills", []) or []:
            cash += -(float(fill["shares_delta"]) * float(fill["price"])) - float(
                fill.get("commission", 0.0)
            )
        per_date[date] = per_date.get(date, 0.0) + cash
    if not per_date:
        return pd.Series(dtype=float)
    return pd.Series(per_date).sort_index().cumsum()


def slice_nav_series(
    ledger: dict, strategy: str, closes: Dict[str, pd.Series]
) -> pd.Series:
    """NAV(t) = sum_symbol shares(t) * close_base(t) + cash(t), from first event.

    ``closes`` maps symbol -> base-currency close Series (see load_close_series).
    Shares/cash are step functions forward-filled onto the market close dates.
    """
    shares = slice_holdings_series(ledger, strategy)
    if shares.empty:
        return pd.Series(dtype=float)
    cash = _slice_cash_series(ledger, strategy)
    first = shares.index[0]

    symbols = [s for s in shares.columns if s in closes and not closes[s].empty]
    if not symbols:
        # No priceable holdings — NAV is just cash on event dates.
        return cash[cash.index >= first]

    close_df = pd.DataFrame({s: closes[s] for s in symbols}).sort_index()
    close_df = close_df[close_df.index >= first]
    if close_df.empty:
        return cash[cash.index >= first]

    shares_on_dates = (
        shares[symbols].reindex(close_df.index, method="ffill").fillna(0.0)
    )
    cash_on_dates = cash.reindex(close_df.index, method="ffill").fillna(0.0)
    nav = (shares_on_dates * close_df).sum(axis=1) + cash_on_dates
    return nav


def load_close_series(
    symbols: List[str], cache_dir: str = "data/cache"
) -> Dict[str, pd.Series]:
    """Newest cached close Series per symbol, scaled to GBP base.

    Local imports keep this module free of heavy/data-layer imports at module
    load time (it stays a pure ledger module).
    """
    from data.cache import HistoricalDataCache, load_price_units

    units = load_price_units()
    scale_map = units.get("scale_to_base", {})
    cache = HistoricalDataCache(cache_dir=cache_dir)
    out: Dict[str, pd.Series] = {}
    for sym in symbols:
        df = cache.load_best_cached_data(sym)
        if df is None or df.empty:
            continue
        col = df["close"] if "close" in df.columns else df.iloc[:, 0]
        out[sym] = col.astype(float) * float(scale_map.get(sym, 1.0))
    return out
