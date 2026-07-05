"""
Forward-looking live-risk blueprint.

Read-only. Pulls current IB positions (or a cached snapshot when IB Gateway is
offline) and reports parametric/historical risk metrics plus drift from a
strategy's target weights. This module NEVER places, modifies, or cancels
orders — it only reads positions and prices and computes analytics.

Endpoints:
    GET /live-risk            -> the live-risk HTML page
    GET /api/live-risk        -> JSON risk payload (positions, VaR/CVaR, HHI,
                                 correlation, drift). Always returns a
                                 well-formed payload; on IB failure it sets
                                 ``ib_online=false`` and a banner instead of 500.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd
from flask import Blueprint, jsonify, render_template, request

from analytics.blend import (
    blended_target_weights,
    latest_target_weights,
    load_blend,
    save_blend,
)
from analytics.metrics import calculate_cvar, calculate_var
from backtesting.results_schema import STRATEGY_FILES
from data.cache import HistoricalDataCache, close_price_base, load_price_units

logger = logging.getLogger(__name__)

risk_bp = Blueprint("risk", __name__, template_folder="templates")

RESULTS_DIR = Path("results")
CACHED_POSITIONS = RESULTS_DIR / "live_positions.json"
DRIFT_THRESHOLD = 0.05  # ±5% flagged
# Symbols held but excluded from all analysis (e.g. a freebie never traded).
IGNORED_SYMBOLS = {"IBKR"}


@risk_bp.route("/live-risk")
def live_risk_page():
    """Serve the live-risk page."""
    return render_template("live_risk.html")


def _enrich_positions(positions: list) -> list:
    """Drop ignored symbols and backfill missing prices from the close cache.

    IB returns a zero/NaN market price when there is no live market-data
    subscription; in that case we value the position at ``shares × latest
    cached close`` so weights and risk metrics still compute.
    """
    units = load_price_units()
    enriched = []
    for p in positions:
        symbol = p.get("symbol")
        if symbol in IGNORED_SYMBOLS:
            continue
        shares = float(p.get("shares", 0.0))
        price = float(p.get("price", 0.0) or 0.0)
        value = float(p.get("value", 0.0) or 0.0)
        if price <= 0 or value <= 0:
            close = close_price_base(symbol, units)
            if close is not None:
                price = close
                value = close * shares
        enriched.append(
            {"symbol": symbol, "shares": shares, "price": price, "value": value}
        )
    return enriched


def _load_positions():
    """
    Return (positions, ib_online, as_of).

    positions: list of {symbol, shares, price, value}. Tries IB first; on any
    failure falls back to a cached snapshot (results/live_positions.json) so the
    page renders with a stale-data banner rather than an error. Ignored symbols
    are dropped and missing prices backfilled from the close cache.
    """
    try:
        import asyncio

        from ib_wrapper.client import IBClient  # imported lazily

        async def _fetch():
            client = IBClient()
            await client.connect()
            try:
                return await client.get_positions()
            finally:
                client.disconnect()  # synchronous — do not await

        raw = asyncio.run(asyncio.wait_for(_fetch(), timeout=10))
        positions = _enrich_positions(
            [
                {
                    "symbol": p.symbol,
                    "shares": float(p.position),
                    "price": float(p.market_price),
                    "value": float(p.market_value),
                }
                for p in raw
                if p.position
            ]
        )
        as_of = pd.Timestamp.now("UTC").isoformat()
        return positions, True, as_of
    except Exception as exc:  # IB offline / not installed / no gateway
        logger.info("IB unavailable (%s); using cached positions if present.", exc)

    if CACHED_POSITIONS.exists():
        try:
            data = json.loads(CACHED_POSITIONS.read_text())
            return (
                _enrich_positions(data.get("positions", [])),
                False,
                data.get("as_of", "unknown"),
            )
        except Exception as exc:
            logger.warning("Failed to read cached positions: %s", exc)
    return [], False, None


def _price_returns(symbols: List[str]) -> pd.DataFrame:
    """Load recent daily returns for each symbol from the parquet cache."""
    cache = HistoricalDataCache()
    series = {}
    for sym in symbols:
        candidates = sorted(
            cache.cache_dir.glob(f"{sym}_*.parquet"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            continue
        try:
            df = pd.read_parquet(candidates[0])
        except Exception:
            continue
        col = "close" if "close" in df.columns else df.columns[-1]
        series[sym] = df[col].pct_change().dropna()
    if not series:
        return pd.DataFrame()
    return pd.DataFrame(series).dropna(how="any")


def _hhi(weights: np.ndarray) -> float:
    """Herfindahl–Hirschman concentration index of |weights| (0..1)."""
    w = np.abs(weights)
    total = w.sum()
    if total == 0:
        return 0.0
    shares = w / total
    return float(np.sum(shares**2))


def _target_weights(strategy_key: Optional[str]) -> dict:
    """Latest target weights from a single strategy's saved weights_history."""
    if not strategy_key:
        return {}
    return latest_target_weights(strategy_key, RESULTS_DIR)


@risk_bp.route("/api/live-risk")
def api_live_risk():
    """Compute the live-risk payload (always well-formed; never raises to 500)."""
    strategy_key = request.args.get("strategy")
    positions, ib_online, as_of = _load_positions()

    total_value = sum(p["value"] for p in positions) or 0.0
    weights = {}
    if total_value > 0:
        weights = {p["symbol"]: p["value"] / total_value for p in positions}

    # Source of the weights the risk metrics are computed from:
    #   ib_live         — live IB positions
    #   cached_snapshot — results/live_positions.json (IB offline)
    #   target_weights  — no positions at all; fall back to a strategy's latest
    #                     target weights so the tab still shows a risk profile
    #   none            — nothing to show
    if ib_online:
        source = "ib_live"
    elif positions:
        source = "cached_snapshot"
    else:
        source = "none"

    # Drift/hypothetical target: an explicit ?strategy=<key> overrides; else the
    # user's saved preferred blend (a weighted sum of the strategies they like).
    blend = load_blend()
    if strategy_key:
        targets = _target_weights(strategy_key)
        target_source = f"strategy:{strategy_key}"
        target_label = f"'{strategy_key}'"
    elif blend:
        targets = blended_target_weights(blend)
        target_source = "blend"
        target_label = "your preferred blend"
    else:
        targets = {}
        target_source = None
        target_label = None

    hypothetical = False
    if not weights and targets:
        # B: no live/cached positions — drive the metrics off the target
        # allocation (blend or single strategy) as a hypothetical portfolio.
        weights = dict(targets)
        source = "target_weights"
        hypothetical = True

    if source == "target_weights":
        banner = (
            f"No live positions — showing hypothetical risk for {target_label} "
            f"target weights (not your actual portfolio)."
        )
    elif source == "cached_snapshot":
        banner = "IB Gateway offline — showing cached/last-known positions."
    elif source == "none":
        banner = (
            "No position data. Connect IB and run "
            "`python scripts/snapshot_positions.py`, or set a preferred blend "
            "below to see its target-allocation risk profile."
        )
    else:
        banner = None

    payload = {
        "ib_online": ib_online,
        "source": source,
        "target_source": target_source,
        "hypothetical": hypothetical,
        "as_of": as_of,
        "banner": banner,
        "positions": positions,
        "weights": weights,
        "total_value": total_value,
        "var_95": None,
        "var_99": None,
        "cvar_95": None,
        "hhi": _hhi(np.array(list(weights.values()))) if weights else 0.0,
        "correlation": {},
        "drift": [],
    }

    symbols = list(weights.keys())
    returns = _price_returns(symbols) if symbols else pd.DataFrame()
    if not returns.empty and weights:
        cols = [s for s in symbols if s in returns.columns]
        if cols:
            w = np.array([weights[s] for s in cols])
            w = w / w.sum() if w.sum() else w
            port_returns = returns[cols].to_numpy() @ w
            port = pd.Series(port_returns)
            payload["var_95"] = round(calculate_var(port, 0.95), 5)
            payload["var_99"] = round(calculate_var(port, 0.99), 5)
            payload["cvar_95"] = round(calculate_cvar(port, 0.95), 5)
            payload["correlation"] = returns[cols].corr().round(3).to_dict()

    # Drift vs target weights — only meaningful against real held positions,
    # not against the hypothetical target-weights portfolio (drift would be 0).
    if targets and not hypothetical:
        all_syms = sorted(set(weights) | set(targets))
        for sym in all_syms:
            cur = weights.get(sym, 0.0)
            tgt = targets.get(sym, 0.0)
            drift = cur - tgt
            payload["drift"].append(
                {
                    "symbol": sym,
                    "current_weight": round(cur, 4),
                    "target_weight": round(tgt, 4),
                    "drift": round(drift, 4),
                    "flagged": abs(drift) > DRIFT_THRESHOLD,
                }
            )

    return jsonify(payload)


def _available_strategies() -> List[str]:
    """Strategy keys with a saved weights_history.json (blend candidates)."""
    root = RESULTS_DIR / "strategies"
    if not root.exists():
        return []
    return sorted(
        d.name
        for d in root.iterdir()
        if d.is_dir()
        and (d / STRATEGY_FILES["weights_history"]).exists()
        and not d.name.endswith("__pbo_sweep")
    )


@risk_bp.route("/api/preferred-blend", methods=["GET"])
def api_get_blend():
    """Return the saved blend, its resolved target weights, and picker options."""
    blend = load_blend()
    return jsonify(
        {
            "blend": blend,
            "target_weights": blended_target_weights(blend) if blend else {},
            "available_strategies": _available_strategies(),
        }
    )


@risk_bp.route("/api/target-allocation")
def api_target_allocation():
    """Target book for the saved blend at a given £ budget: per-asset weight,
    amount, close price, and share count (a from-cash allocation, not drift)."""
    try:
        budget = float(request.args.get("budget", 0) or 0)
    except (TypeError, ValueError):
        budget = 0.0
    blend = load_blend()
    target = blended_target_weights(blend) if blend else {}
    units = load_price_units()
    rows = []
    for sym, w in sorted(target.items(), key=lambda kv: -kv[1]):
        price = close_price_base(sym, units)
        amount = w * budget
        shares = (amount / price) if price else None
        rows.append(
            {
                "symbol": sym,
                "weight": round(w, 4),
                "amount": round(amount, 2),
                "price": round(price, 2) if price else None,
                "shares": round(shares, 2) if shares is not None else None,
            }
        )
    return jsonify({"budget": budget, "blend": blend, "target": rows})


@risk_bp.route("/api/preferred-blend", methods=["POST"])
def api_save_blend():
    """Persist a blend {strategy_key: weight}; returns saved blend + target."""
    body = request.get_json(silent=True) or {}
    blend = body.get("blend", body)
    try:
        saved = save_blend({str(k): v for k, v in blend.items()})
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"blend": saved, "target_weights": blended_target_weights(saved)})
