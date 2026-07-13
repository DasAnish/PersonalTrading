#!/usr/bin/env python3
"""Grade pre-registered strategies against realized live drawdowns.

Reads the live NAV histories (whole-account + per-slice) and each strategy's
frozen registration, then writes ``results/registration_status.json`` mapping
strategy -> {status, realized_dd, portfolio_dd, envelope_dd, reasons}. A soft
nightly step: absence of data yields ``ok``/empty, never an abort. Read-only —
never trades.

Usage:
    python scripts/check_registrations.py
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from analytics.registrations import evaluate_all, load_all_registrations  # noqa: E402

logger = logging.getLogger(__name__)

TRACKING_DIR = Path("live_tracking")
NAV_CSV = TRACKING_DIR / "nav_history.csv"
SLICE_NAV_CSV = TRACKING_DIR / "slice_nav_history.csv"
STATUS_PATH = Path("results") / "registration_status.json"


def _portfolio_nav() -> pd.Series | None:
    """Whole-account net-liquidation series indexed by date."""
    if not NAV_CSV.exists():
        return None
    df = pd.read_csv(NAV_CSV)
    if df.empty or "net_liquidation" not in df.columns:
        return None
    df = df.dropna(subset=["net_liquidation"])
    s = pd.Series(
        df["net_liquidation"].astype(float).values,
        index=pd.to_datetime(df["date"]),
    ).sort_index()
    return s if len(s) >= 2 else None


def _slice_navs() -> dict[str, pd.Series]:
    """Per-strategy slice_value series indexed by date."""
    if not SLICE_NAV_CSV.exists():
        return {}
    df = pd.read_csv(SLICE_NAV_CSV)
    if df.empty or "slice_value" not in df.columns:
        return {}
    out: dict[str, pd.Series] = {}
    for strat, grp in df.groupby("strategy"):
        grp = grp.dropna(subset=["slice_value"]).sort_values("date")
        s = pd.Series(
            grp["slice_value"].astype(float).values,
            index=pd.to_datetime(grp["date"]),
        )
        out[str(strat)] = s
    return out


def check_registrations() -> dict:
    registrations = load_all_registrations()
    if not registrations:
        logger.info("No registrations to check.")
        return {}
    status = evaluate_all(registrations, _slice_navs(), _portfolio_nav())
    breaches = [k for k, v in status.items() if v["status"] == "breach"]
    if breaches:
        logger.warning(f"Registration BREACH: {', '.join(breaches)}")
    return status


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    status = check_registrations()
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    logger.info(f"Wrote {len(status)} registration statuses -> {STATUS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
