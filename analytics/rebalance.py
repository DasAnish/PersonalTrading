"""
Pure, testable rebalance-delta computation.

This module deliberately contains **no IB imports, no side effects, and no
order-placement code**. It only computes the arithmetic difference between
a portfolio's current holdings and a target allocation — the same
computation the ``rebalance`` skill (``.claude/skills/rebalance/SKILL.md``)
used to do as free-form LLM arithmetic. Backing it with tested Python here
means the numbers in a rebalance report are reproducible and unit-tested,
not re-derived by the model on every run.

Per the project's standing rule (see ``CLAUDE.md``): all orders are entered
manually by the user in IB Gateway. Nothing in this module — or in
``scripts/rebalance_report.py``, which prints its output — submits,
modifies, or cancels any order. It only produces a report.

Design notes / edge-case decisions:

- **Target weights that don't sum to 1.0 are normalized**, not rejected.
  ``compute_rebalance_plan`` divides every target weight by their sum so
  they sum to exactly 1.0, and records a note on the returned
  ``RebalancePlan`` explaining that it did so (and by what factor). If the
  weights sum to zero or less, normalization is impossible; the plan falls
  back to treating every target weight as 0 (i.e. "sell everything") and
  records a note rather than raising or dividing by zero.
- **Cash is included in total portfolio value** and is available for
  redeployment across the normalized target weights — i.e. target weights
  are interpreted as a fraction of (holdings value + cash), not of
  holdings value alone.
- **Zero or missing prices are skipped, not crashed on.** A symbol whose
  price is missing, zero, or negative gets a ``HOLD`` entry with
  ``skipped=True`` and an explanatory note; its current value is excluded
  from the portfolio total (since it's unknown) and no trade is suggested
  for it.
- **HOLD threshold**: a small default weight-delta threshold
  (``DEFAULT_HOLD_THRESHOLD = 0.001``, i.e. 0.1 percentage points) below
  which a symbol is marked ``HOLD`` instead of ``BUY``/``SELL``, so trivial
  drift doesn't generate a "trade" for a few pence. Pass
  ``hold_threshold=0.0`` to disable and always trade on any nonzero delta.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

DEFAULT_HOLD_THRESHOLD = 0.001  # 0.1 percentage points of portfolio weight


@dataclass
class RebalanceEntry:
    """Per-symbol rebalance detail."""

    symbol: str
    current_shares: float
    current_price: Optional[float]
    current_value: float
    current_weight: float
    target_weight: float
    delta_weight: float
    target_value: float
    delta_value: float
    est_shares: float  # signed: positive = buy this many shares, negative = sell
    direction: str  # "BUY", "SELL", or "HOLD"
    skipped: bool = False
    note: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "current_shares": self.current_shares,
            "current_price": self.current_price,
            "current_value": self.current_value,
            "current_weight": self.current_weight,
            "target_weight": self.target_weight,
            "delta_weight": self.delta_weight,
            "target_value": self.target_value,
            "delta_value": self.delta_value,
            "est_shares": self.est_shares,
            "direction": self.direction,
            "skipped": self.skipped,
            "note": self.note,
        }


@dataclass
class RebalancePlan:
    """Full rebalance plan: per-symbol entries plus portfolio-level totals."""

    entries: List[RebalanceEntry]
    total_portfolio_value: float
    total_turnover: float  # sum of |delta_value| across non-skipped entries
    cash: float
    weights_normalized: bool
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "entries": [e.to_dict() for e in self.entries],
            "total_portfolio_value": self.total_portfolio_value,
            "total_turnover": self.total_turnover,
            "cash": self.cash,
            "weights_normalized": self.weights_normalized,
            "notes": self.notes,
        }


def compute_rebalance_plan(
    positions: Dict[str, float],
    prices: Dict[str, float],
    target_weights: Dict[str, float],
    cash: float = 0.0,
    hold_threshold: float = DEFAULT_HOLD_THRESHOLD,
) -> RebalancePlan:
    """
    Compute the delta between current holdings and a target allocation.

    Args:
        positions: symbol -> current shares held. A symbol present here but
            absent from ``target_weights`` is treated as a full exit
            (target weight 0.0).
        prices: symbol -> last known price. Missing, zero, or negative
            prices cause that symbol to be skipped (flagged, not crashed
            on) rather than dividing by zero.
        target_weights: symbol -> target portfolio weight. Does not need to
            sum to 1.0 — see module docstring for the normalization rule.
            A symbol present here but absent from ``positions`` is treated
            as a new buy from zero shares.
        cash: Uninvested cash balance, included in total portfolio value
            and available for redeployment across target weights.
        hold_threshold: Minimum absolute weight delta (as a decimal, e.g.
            0.001 = 0.1%) required to generate a BUY/SELL direction;
            smaller deltas are marked HOLD. Pass 0.0 to disable.

    Returns:
        A ``RebalancePlan`` with one ``RebalanceEntry`` per symbol (union
        of ``positions`` and ``target_weights`` keys) and portfolio-level
        totals.
    """
    notes: List[str] = []

    # --- Normalize target weights -----------------------------------
    weights_sum = sum(target_weights.values())
    weights_normalized = False
    if weights_sum <= 0:
        normalized_weights: Dict[str, float] = {k: 0.0 for k in target_weights}
        if target_weights:
            notes.append(
                "target weights summed to "
                f"{weights_sum:.4f} (<= 0); unable to normalize, all target "
                "weights treated as 0.0 (full exit)."
            )
    elif abs(weights_sum - 1.0) > 1e-9:
        normalized_weights = {k: v / weights_sum for k, v in target_weights.items()}
        weights_normalized = True
        notes.append(
            f"target weights summed to {weights_sum:.4f}; normalized to sum to 1.0."
        )
    else:
        normalized_weights = dict(target_weights)

    symbols = sorted(set(positions) | set(normalized_weights))

    # --- Pass 1: current values, skipping bad prices ------------------
    current_values: Dict[str, float] = {}
    skipped_symbols: Dict[str, str] = {}
    for symbol in symbols:
        shares = positions.get(symbol, 0.0)
        price = prices.get(symbol)
        if price is None or price <= 0:
            skipped_symbols[symbol] = (
                f"price missing or non-positive ({price!r}); symbol skipped, "
                "excluded from portfolio value and turnover."
            )
            current_values[symbol] = 0.0
        else:
            current_values[symbol] = shares * price

    valid_holdings_value = sum(
        v for s, v in current_values.items() if s not in skipped_symbols
    )
    total_portfolio_value = cash + valid_holdings_value

    # --- Pass 2: build entries -----------------------------------------
    entries: List[RebalanceEntry] = []
    total_turnover = 0.0

    for symbol in symbols:
        shares = positions.get(symbol, 0.0)
        price = prices.get(symbol)
        target_w = normalized_weights.get(symbol, 0.0)

        if symbol in skipped_symbols:
            entries.append(
                RebalanceEntry(
                    symbol=symbol,
                    current_shares=shares,
                    current_price=price,
                    current_value=0.0,
                    current_weight=0.0,
                    target_weight=target_w,
                    delta_weight=0.0,
                    target_value=0.0,
                    delta_value=0.0,
                    est_shares=0.0,
                    direction="HOLD",
                    skipped=True,
                    note=skipped_symbols[symbol],
                )
            )
            continue

        current_value = current_values[symbol]
        current_weight = (
            current_value / total_portfolio_value if total_portfolio_value > 0 else 0.0
        )
        delta_weight = target_w - current_weight
        target_value = target_w * total_portfolio_value
        delta_value = target_value - current_value
        est_shares = delta_value / price if price else 0.0

        if abs(delta_weight) < hold_threshold:
            direction = "HOLD"
        elif delta_value > 0:
            direction = "BUY"
        else:
            direction = "SELL"

        entries.append(
            RebalanceEntry(
                symbol=symbol,
                current_shares=shares,
                current_price=price,
                current_value=current_value,
                current_weight=current_weight,
                target_weight=target_w,
                delta_weight=delta_weight,
                target_value=target_value,
                delta_value=delta_value,
                est_shares=est_shares,
                direction=direction,
                skipped=False,
                note=None,
            )
        )
        total_turnover += abs(delta_value)

    return RebalancePlan(
        entries=entries,
        total_portfolio_value=total_portfolio_value,
        total_turnover=total_turnover,
        cash=cash,
        weights_normalized=weights_normalized,
        notes=notes,
    )
