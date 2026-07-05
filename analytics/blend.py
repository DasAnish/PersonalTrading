"""
Preferred-strategy blend: a user-curated weighted sum of strategies.

The user picks several strategies they like and assigns each a weight; the
blended target allocation is the weighted sum of those strategies' latest
target weights (per asset), normalized to sum to 1. This blended target drives
the live-risk drift view and the rebalance report.

The blend is persisted in ``config/preferred_blend.json``:

    {"blend": {"hrp_commodity_theme": 0.4, "adaptive_asset_allocation": 0.6}}

This module only reads saved backtest weights and reads/writes the local blend
config file. It never touches IB or places any order.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict

from backtesting.results_schema import STRATEGY_FILES, strategy_dir

logger = logging.getLogger(__name__)

BLEND_CONFIG = Path("config") / "preferred_blend.json"
RESULTS_DIR = Path("results")


def load_blend(path: Path = BLEND_CONFIG) -> Dict[str, float]:
    """Return the saved blend ``{strategy_key: weight}`` (empty if none)."""
    if not Path(path).exists():
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not read blend config %s: %s", path, exc)
        return {}
    blend = data.get("blend", {})
    return {
        str(k): float(v)
        for k, v in blend.items()
        if isinstance(v, (int, float)) and v > 0
    }


def save_blend(blend: Dict[str, float], path: Path = BLEND_CONFIG) -> Dict[str, float]:
    """Validate and persist a blend; returns the cleaned blend that was saved.

    Drops non-positive/non-numeric weights. Raises ValueError if the result is
    empty (nothing worth saving).
    """
    cleaned = {
        str(k): float(v)
        for k, v in blend.items()
        if isinstance(v, (int, float)) and float(v) > 0
    }
    if not cleaned:
        raise ValueError("Blend must contain at least one strategy with weight > 0.")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"blend": cleaned}, f, indent=2)
        f.write("\n")
    return cleaned


def latest_target_weights(
    strategy_key: str, results_dir: Path = RESULTS_DIR
) -> Dict[str, float]:
    """Latest target weights ``{symbol: weight}`` from a strategy's history."""
    path = strategy_dir(results_dir, strategy_key) / STRATEGY_FILES["weights_history"]
    if not path.exists():
        return {}
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not rows:
        return {}
    last = rows[-1]
    return {
        k: float(v)
        for k, v in last.items()
        if k not in ("date", "timestamp") and isinstance(v, (int, float))
    }


def blended_target_weights(
    blend: Dict[str, float], results_dir: Path = RESULTS_DIR
) -> Dict[str, float]:
    """Weighted sum of each strategy's latest target weights, normalized.

    ``blend`` maps strategy_key -> blend weight. Strategies with no saved
    weights are skipped. Returns ``{symbol: weight}`` summing to 1 (empty if
    nothing usable).
    """
    combined: Dict[str, float] = {}
    for key, blend_w in blend.items():
        targets = latest_target_weights(key, results_dir)
        if not targets:
            logger.info("Blend: no saved weights for '%s'; skipping.", key)
            continue
        for symbol, w in targets.items():
            combined[symbol] = combined.get(symbol, 0.0) + blend_w * w

    total = sum(combined.values())
    if total <= 0:
        return {}
    return {symbol: w / total for symbol, w in combined.items()}
