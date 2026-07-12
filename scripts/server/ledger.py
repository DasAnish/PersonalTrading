"""Read/record API for the virtual per-strategy allocation ledger.

Exposes the derived slice state (analytics/ledger.py) and a single write
endpoint that records trades the user already executed MANUALLY in IB. This
module NEVER places, modifies, or cancels any order — mark-traded only appends
to the ledger.
"""

import csv
from pathlib import Path

from flask import Blueprint, jsonify, request

from analytics.ledger import (
    append_event,
    cash_by_strategy,
    holdings_by_strategy,
    load_close_series,
    load_ledger,
    personal_holdings,
    reconcile,
    slice_nav_series,
    slice_value,
)
from analytics.blend import latest_target_weights
from analytics.rebalance import compute_rebalance_plan
from data.cache import close_price_base

from .risk import _load_positions
from .jobs import _definition_exists

ledger_bp = Blueprint("ledger", __name__)

RESULTS_DIR = Path("results")
NAV_HISTORY = Path("live_tracking") / "nav_history.csv"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _price_for(symbol: str, live_prices: dict) -> float:
    """Live price if present/positive, else the cached base-currency close."""
    live = live_prices.get(symbol)
    if live and live > 0:
        return float(live)
    base = close_price_base(symbol)
    return float(base) if base else 0.0


def _prices_for(symbols, live_prices: dict) -> dict:
    return {s: _price_for(s, live_prices) for s in symbols}


def _total_cash() -> float | None:
    """Latest total account cash from the nightly NAV snapshot (offline-safe)."""
    if not NAV_HISTORY.exists():
        return None
    try:
        with open(NAV_HISTORY, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            return None
        return float(rows[-1].get("total_cash") or 0.0)
    except Exception:
        return None


def _slice_summary(key: str, holdings: dict, cash: float, prices: dict) -> dict:
    values = {s: sh * prices.get(s, 0.0) for s, sh in holdings.items()}
    holdings_value = sum(values.values())
    return {
        "holdings": holdings,
        "cash": cash,
        "values": values,
        "slice_value": holdings_value + cash,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@ledger_bp.route("/api/ledger")
def api_ledger():
    positions, ib_online, as_of = _load_positions()
    ib_pos = {p["symbol"]: p["shares"] for p in positions}
    live_prices = {p["symbol"]: p["price"] for p in positions}

    ledger = load_ledger()
    hbs = holdings_by_strategy(ledger)
    cbs = cash_by_strategy(ledger)

    symbols = set(ib_pos) | {s for book in hbs.values() for s in book}
    prices = _prices_for(symbols, live_prices)

    strategies = {
        key: _slice_summary(key, holdings, cbs.get(key, 0.0), prices)
        for key, holdings in hbs.items()
    }

    personal = personal_holdings(ib_pos, ledger)
    personal_value = slice_value(personal, prices)

    total_cash = _total_cash()
    slice_cash_total = sum(cbs.values())
    unallocated_cash = None if total_cash is None else total_cash - slice_cash_total

    return jsonify(
        {
            "ib_online": ib_online,
            "as_of": as_of,
            "strategies": strategies,
            "personal": {"holdings": personal, "value": personal_value},
            "unallocated_cash": unallocated_cash,
            "reconciliation": reconcile(ib_pos, ledger),
            "events_count": len(ledger.get("events", [])),
        }
    )


@ledger_bp.route("/api/ledger/mark-traded", methods=["POST"])
def api_mark_traded():
    """Record a trade the user ALREADY executed manually in IB. Never trades."""
    body = request.get_json(silent=True) or {}
    strategy = body.get("strategy")
    if not strategy or not _definition_exists(strategy):
        return jsonify({"error": f"unknown strategy: {strategy!r}"}), 400

    event = {
        "strategy": strategy,
        "trade_date": body.get("trade_date"),
        "external_cash_delta": body.get("external_cash_delta", 0.0),
        "fills": body.get("fills", []),
        "note": body.get("note", ""),
    }
    try:
        stored = append_event(event)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    ledger = load_ledger()
    holdings = holdings_by_strategy(ledger).get(strategy, {})
    cash = cash_by_strategy(ledger).get(strategy, 0.0)
    positions, _, _ = _load_positions()
    prices = _prices_for(holdings, {p["symbol"]: p["price"] for p in positions})
    return (
        jsonify(
            {
                "event": stored,
                "slice": _slice_summary(strategy, holdings, cash, prices),
            }
        ),
        201,
    )


@ledger_bp.route("/api/ledger/slice-plan/<strategy>")
def api_slice_plan(strategy):
    """Prefill for mark-as-traded: rebalance this slice to its target weights."""
    budget = float(request.args.get("budget", 0.0) or 0.0)
    hold_threshold = float(request.args.get("hold_threshold", 0.001) or 0.001)

    ledger = load_ledger()
    holdings = holdings_by_strategy(ledger).get(strategy, {})
    slice_cash = cash_by_strategy(ledger).get(strategy, 0.0)
    weights = latest_target_weights(strategy, RESULTS_DIR)

    symbols = set(holdings) | set(weights)
    prices = _prices_for(symbols, {})  # slice plan uses cached base prices
    plan = compute_rebalance_plan(
        holdings,
        prices,
        weights,
        cash=slice_cash + budget,
        hold_threshold=hold_threshold,
    )
    out = plan.to_dict()
    out.update({"strategy": strategy, "slice_cash": slice_cash, "budget": budget})
    return jsonify(out)


@ledger_bp.route("/api/ledger/slice/<strategy>/nav")
def api_slice_nav(strategy):
    ledger = load_ledger()
    holdings = holdings_by_strategy(ledger).get(strategy, {})
    closes = load_close_series(list(holdings))
    nav = slice_nav_series(ledger, strategy, closes)
    series = [
        {"date": d.strftime("%Y-%m-%d"), "value": float(v)} for d, v in nav.items()
    ]
    first_event = series[0]["date"] if series else None
    return jsonify({"strategy": strategy, "series": series, "first_event": first_event})
