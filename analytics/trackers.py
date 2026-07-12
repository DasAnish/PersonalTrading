"""Watchlist ("trackers") of strategies with paper performance since added.

A tracker records a strategy the user likes and the date they started watching
it. Performance is the strategy's nightly-recomputed portfolio history truncated
at ``added_on`` and normalized to 100 — honest paper-tracking. Caveat: strategy
code changes rewrite history; the nightly vintage stamp covers that.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

from backtesting.results_schema import load_portfolio_values
from analytics.metrics import summarize_performance

TRACKERS_PATH = Path("live_tracking") / "trackers.json"
TRACKERS_SCHEMA_VERSION = 1


def _empty() -> dict:
    return {"schema_version": TRACKERS_SCHEMA_VERSION, "trackers": []}


def load_trackers(path: Path = None) -> dict:
    path = Path(path) if path is not None else TRACKERS_PATH
    if not path.exists():
        return _empty()
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("schema_version", TRACKERS_SCHEMA_VERSION)
    data.setdefault("trackers", [])
    return data


def _write(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def add_tracker(
    strategy: str, note: str = "", added_on: str = None, path: Path = None
) -> dict:
    """Add a tracker. Raises ValueError if the strategy is already tracked."""
    path = Path(path) if path is not None else TRACKERS_PATH
    data = load_trackers(path)
    if any(t["strategy"] == strategy for t in data["trackers"]):
        raise ValueError(f"already tracked: {strategy}")
    entry = {
        "strategy": strategy,
        "added_on": added_on or date.today().isoformat(),
        "note": note or "",
    }
    data["trackers"].append(entry)
    _write(data, path)
    return entry


def remove_tracker(strategy: str, path: Path = None) -> bool:
    """Remove a tracker; returns True if one was removed."""
    path = Path(path) if path is not None else TRACKERS_PATH
    data = load_trackers(path)
    before = len(data["trackers"])
    data["trackers"] = [t for t in data["trackers"] if t["strategy"] != strategy]
    removed = len(data["trackers"]) < before
    if removed:
        _write(data, path)
    return removed


def since_added_performance(
    strategy: str, added_on: str, results_dir: str = "results"
) -> dict:
    """Normalized (=100 at added_on) paper performance from added_on onward."""
    empty = {
        "series": [],
        "total_return": None,
        "sharpe": None,
        "max_drawdown": None,
        "n_points": 0,
    }
    try:
        values = load_portfolio_values(results_dir, strategy)
    except Exception:
        return empty
    if values is None or values.empty:
        return empty

    values = values.sort_index()
    truncated = values[values.index >= pd.Timestamp(added_on)]
    if truncated.empty:
        return empty

    base = float(truncated.iloc[0])
    normalized = truncated / base * 100.0 if base else truncated
    perf = summarize_performance(truncated)
    return {
        "series": [
            {"date": d.strftime("%Y-%m-%d"), "value": float(v)}
            for d, v in normalized.items()
        ],
        "total_return": perf.get("total_return"),
        "sharpe": perf.get("sharpe_ratio"),
        "max_drawdown": perf.get("max_drawdown"),
        "n_points": int(len(truncated)),
    }


def tracker_with_performance(tracker: dict, results_dir: str = "results") -> dict:
    """A tracker entry enriched with its since-added performance block."""
    out = dict(tracker)
    out["since_added"] = since_added_performance(
        tracker["strategy"], tracker["added_on"], results_dir
    )
    return out
