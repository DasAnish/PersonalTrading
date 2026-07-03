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

from analytics.metrics import calculate_cvar, calculate_var
from backtesting.results_schema import STRATEGY_FILES, strategy_dir
from data.cache import HistoricalDataCache

logger = logging.getLogger(__name__)

risk_bp = Blueprint("risk", __name__, template_folder="templates")

RESULTS_DIR = Path("results")
CACHED_POSITIONS = RESULTS_DIR / "live_positions.json"
DRIFT_THRESHOLD = 0.05  # ±5% flagged


@risk_bp.route("/live-risk")
def live_risk_page():
    """Serve the live-risk page."""
    return render_template("live_risk.html")


def _load_positions():
    """
    Return (positions, ib_online, as_of).

    positions: list of {symbol, shares, price, value}. Tries IB first; on any
    failure falls back to a cached snapshot (results/live_positions.json) so the
    page renders with a stale-data banner rather than an error.
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
                await client.disconnect()

        raw = asyncio.run(asyncio.wait_for(_fetch(), timeout=10))
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
        as_of = pd.Timestamp.utcnow().isoformat()
        return positions, True, as_of
    except Exception as exc:  # IB offline / not installed / no gateway
        logger.info("IB unavailable (%s); using cached positions if present.", exc)

    if CACHED_POSITIONS.exists():
        try:
            data = json.loads(CACHED_POSITIONS.read_text())
            return (
                data.get("positions", []),
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
    """Latest target weights from a strategy's saved weights_history.json."""
    if not strategy_key:
        return {}
    path = strategy_dir(RESULTS_DIR, strategy_key) / STRATEGY_FILES["weights_history"]
    if not path.exists():
        return {}
    try:
        rows = json.loads(path.read_text())
        if not rows:
            return {}
        last = rows[-1]
        return {
            k: float(v)
            for k, v in last.items()
            if k not in ("date", "timestamp") and isinstance(v, (int, float))
        }
    except Exception:
        return {}


@risk_bp.route("/api/live-risk")
def api_live_risk():
    """Compute the live-risk payload (always well-formed; never raises to 500)."""
    strategy_key = request.args.get("strategy")
    positions, ib_online, as_of = _load_positions()

    total_value = sum(p["value"] for p in positions) or 0.0
    weights = {}
    if total_value > 0:
        weights = {p["symbol"]: p["value"] / total_value for p in positions}

    payload = {
        "ib_online": ib_online,
        "as_of": as_of,
        "banner": (
            None
            if ib_online
            else "IB Gateway offline — showing cached/last-known data."
        ),
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

    # Drift vs target weights
    targets = _target_weights(strategy_key)
    if targets:
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
