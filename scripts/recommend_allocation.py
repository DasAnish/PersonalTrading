#!/usr/bin/env python3
"""Gather every input the recommend-allocation skill needs into one JSON.

The skill reasons about how to allocate capital across validated strategies; to
keep that reasoning reproducible and auditable it must read a single, tested
state snapshot rather than scraping a dozen files ad hoc. This script assembles
``results/recommendation_input.json`` from: the virtual allocation ledger
(analytics/ledger.py), trackers + since-added paper performance, the
meta-portfolio blend, the selection meta-backtest, each strategy's metrics +
validation verdict + registration status, and the latest account NAV row.

Read-only. It NEVER places, modifies, or cancels an order — it only writes a
local JSON that the skill turns into a recommendation report the user acts on
manually in IB.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analytics.ledger import (  # noqa: E402
    cash_by_strategy,
    holdings_by_strategy,
    load_ledger,
    personal_holdings,
    reconcile,
    slice_value,
)
from data.cache import close_price_base, load_price_units  # noqa: E402

logger = logging.getLogger(__name__)

RESULTS_DIR = Path("results")
TRACKING_DIR = Path("live_tracking")
NAV_CSV = TRACKING_DIR / "nav_history.csv"
LIVE_POSITIONS = RESULTS_DIR / "live_positions.json"
OUT_PATH = RESULTS_DIR / "recommendation_input.json"

# Live-trading constraints (see live_risk_params memory / plan W4).
CONSTRAINTS = {
    "account": "ISA",  # no tax fields / wash-sale rules
    "max_portfolio_drawdown": 0.30,  # kill level
    "phase": "small-real-slice",  # size new slices conservatively
    "note": "Recommendations only — user enters every order manually in IB.",
}


def _load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _ib_positions() -> tuple[dict, dict]:
    """(shares, prices) from results/live_positions.json, or ({}, {}) if absent."""
    data = _load_json(LIVE_POSITIONS)
    if not data:
        return {}, {}
    shares, prices = {}, {}
    for p in data.get("positions", []):
        sym = p.get("symbol")
        if not sym:
            continue
        shares[sym] = float(p.get("shares", 0.0))
        prices[sym] = float(p.get("price", 0.0) or 0.0)
    return shares, prices


def _prices_for(symbols, live_prices: dict) -> dict:
    units = load_price_units()
    out = {}
    for s in symbols:
        lp = live_prices.get(s)
        if lp and lp > 0:
            out[s] = float(lp)
        else:
            base = close_price_base(s, units)
            out[s] = float(base) if base else 0.0
    return out


def _latest_nav_row() -> dict | None:
    if not NAV_CSV.exists():
        return None
    try:
        with open(NAV_CSV, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        return rows[-1] if rows else None
    except Exception:
        return None


def _ledger_block() -> dict:
    ib_shares, live_prices = _ib_positions()
    ledger = load_ledger()
    hbs = holdings_by_strategy(ledger)
    cbs = cash_by_strategy(ledger)
    symbols = set(ib_shares) | {s for book in hbs.values() for s in book}
    prices = _prices_for(symbols, live_prices)

    strategies = {}
    for key, holdings in hbs.items():
        hv = slice_value(holdings, prices)
        cash = cbs.get(key, 0.0)
        strategies[key] = {
            "holdings": holdings,
            "cash": round(cash, 2),
            "slice_value": round(hv + cash, 2),
        }
    personal = personal_holdings(ib_shares, ledger)
    return {
        "strategies": strategies,
        "personal": {
            "holdings": personal,
            "value": round(slice_value(personal, prices), 2),
        },
        "reconciliation": reconcile(ib_shares, ledger),
        "ib_positions_available": bool(ib_shares),
    }


def _strategies_block() -> dict:
    """Per-strategy metrics + validation verdict + registration status."""
    index = _load_json(RESULTS_DIR / "strategies_index.json") or {}
    reg_status = _load_json(RESULTS_DIR / "registration_status.json") or {}
    entries = index.get("strategies", {})
    out = {}
    for key, entry in entries.items():
        m = entry.get("metrics", {}) or {}
        validation = (
            _load_json(RESULTS_DIR / "strategies" / key / "validation.json") or {}
        )
        out[key] = {
            "sharpe": m.get("sharpe_ratio"),
            "cagr": m.get("cagr"),
            "total_return": m.get("total_return"),
            "max_drawdown": m.get("max_drawdown"),
            "data_end": m.get("data_end"),
            "validation": validation.get("overall"),
            "registration": (reg_status.get(key) or {}).get("status"),
        }
    return out


def _trackers_block() -> list:
    try:
        from analytics.trackers import load_trackers, tracker_with_performance

        return [
            tracker_with_performance(t) for t in load_trackers().get("trackers", [])
        ]
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"Could not load trackers: {exc}")
        return []


def _meta_portfolio_block() -> dict | None:
    mp = _load_json(RESULTS_DIR / "meta_portfolio.json")
    if not mp:
        return None
    # Drop the bulky correlation matrix; keep the decision-relevant parts.
    return {k: v for k, v in mp.items() if k != "correlation_matrix"}


def gather(results_dir: Path = RESULTS_DIR) -> dict:
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "constraints": CONSTRAINTS,
        "account_nav": _latest_nav_row(),
        "ledger": _ledger_block(),
        "trackers": _trackers_block(),
        "meta_portfolio": _meta_portfolio_block(),
        "meta_selection": _load_json(results_dir / "meta_selection.json"),
        "strategies": _strategies_block(),
    }


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    payload = gather()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    n_strat = len(payload["strategies"])
    n_slices = len(payload["ledger"]["strategies"])
    logger.info(
        f"Wrote recommendation input: {n_strat} strategies, {n_slices} live "
        f"slices, {len(payload['trackers'])} trackers -> {OUT_PATH}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
