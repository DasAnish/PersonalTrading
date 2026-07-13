"""
Standalone CLI: compute and print a rebalance plan from JSON inputs.

Backs the ``rebalance`` skill (``.claude/skills/rebalance/SKILL.md``) with
tested Python arithmetic instead of free-form LLM computation. Reads
current positions, last prices, and target weights from JSON files (or
inline JSON strings), computes the plan via
``analytics.rebalance.compute_rebalance_plan``, and prints it as a table.

This script NEVER places, submits, modifies, or cancels any order — it
only prints a report. All orders are entered manually by the user in IB
Gateway (see CLAUDE.md).

Input JSON shapes:
    positions.json: {"VUSA": 100.0, "VWRL": 50.0}         # symbol -> shares
    prices.json:    {"VUSA": 95.23, "VWRL": 110.50}        # symbol -> last price
    weights.json:   {"VUSA": 0.6, "VWRL": 0.4}              # symbol -> target weight

Usage:
    python scripts/rebalance_report.py \\
        --positions positions.json --prices prices.json \\
        --weights weights.json --cash 500.0

    # Or pass inline JSON directly:
    python scripts/rebalance_report.py \\
        --positions-json '{"VUSA": 100}' --prices-json '{"VUSA": 95.23}' \\
        --weights-json '{"VUSA": 1.0}' --cash 0
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analytics.blend import (
    blended_target_weights,
    latest_target_weights,
    load_blend,
)
from analytics.ledger import cash_by_strategy, holdings_by_strategy, load_ledger
from analytics.rebalance import DEFAULT_HOLD_THRESHOLD, compute_rebalance_plan
from data.cache import close_price_base, load_price_units

SNAPSHOT_PATH = Path("results") / "live_positions.json"
IGNORED_SYMBOLS = {"IBKR"}


def _load_dict_arg(file_path: str | None, inline_json: str | None, label: str) -> dict:
    if inline_json is not None:
        return json.loads(inline_json)
    if file_path is not None:
        with open(file_path, "r") as f:
            return json.load(f)
    raise SystemExit(f"Must supply either --{label} <file> or --{label}-json <json>")


def _load_snapshot() -> tuple[dict, dict]:
    """Return (positions {symbol: shares}, prices {symbol: price}) from the
    live-positions snapshot, backfilling missing prices from the close cache
    and dropping ignored symbols."""
    if not SNAPSHOT_PATH.exists():
        raise SystemExit(
            f"{SNAPSHOT_PATH} not found — run `python scripts/snapshot_positions.py` "
            "while IB Gateway is connected first."
        )
    data = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    units = load_price_units()
    positions, prices = {}, {}
    for p in data.get("positions", []):
        symbol = p.get("symbol")
        if symbol in IGNORED_SYMBOLS:
            continue
        shares = float(p.get("shares", 0.0))
        price = float(p.get("price", 0.0) or 0.0)
        if price <= 0:
            close = close_price_base(symbol, units)
            price = close if close is not None else 0.0
        positions[symbol] = shares
        prices[symbol] = price
    return positions, prices


def print_plan_table(plan) -> None:
    print()
    header = (
        f"{'Symbol':<10} {'Cur Wt':>8} {'Tgt Wt':>8} {'Δ Wt':>8} "
        f"{'Cur Val':>12} {'Tgt Val':>12} {'Δ Val':>12} {'Est Shares':>11} {'Action':<6}"
    )
    print(header)
    print("-" * len(header))
    for e in plan.entries:
        if e.skipped:
            print(
                f"{e.symbol:<10} {'--':>8} {'--':>8} {'--':>8} {'--':>12} {'--':>12} {'--':>12} {'--':>11} {'SKIP':<6}  ({e.note})"
            )
            continue
        print(
            f"{e.symbol:<10} {e.current_weight*100:>7.2f}% {e.target_weight*100:>7.2f}% "
            f"{e.delta_weight*100:>+7.2f}% {e.current_value:>12,.2f} {e.target_value:>12,.2f} "
            f"{e.delta_value:>+12,.2f} {e.est_shares:>+11,.2f} {e.direction:<6}"
        )
    print("-" * len(header))
    print(f"Cash: {plan.cash:,.2f}")
    print(f"Total portfolio value: {plan.total_portfolio_value:,.2f}")
    print(f"Total turnover (sum |Δ value|): {plan.total_turnover:,.2f}")
    if plan.weights_normalized:
        print("Note: target weights did not sum to 1.0 and were normalized.")
    for note in plan.notes:
        print(f"Note: {note}")
    print()
    print(
        "IMPORTANT: this is a report only. Enter all orders manually in IB "
        "Gateway — nothing here places, submits, modifies, or cancels trades."
    )


def main() -> None:
    # The table header uses Δ; ensure UTF-8 output on Windows (cp1252 console).
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        description="Compute a rebalance plan (current holdings vs target weights) "
        "and print it as a table. Report only — never places orders.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/rebalance_report.py --positions positions.json --prices prices.json \\
      --weights weights.json --cash 500.0

  python scripts/rebalance_report.py --positions-json '{"VUSA": 100}' \\
      --prices-json '{"VUSA": 95.23}' --weights-json '{"VUSA": 1.0}' --cash 0
        """,
    )
    parser.add_argument(
        "--positions",
        type=str,
        default=None,
        help="Path to positions JSON (symbol -> shares).",
    )
    parser.add_argument(
        "--positions-json", type=str, default=None, help="Inline positions JSON."
    )
    parser.add_argument(
        "--prices",
        type=str,
        default=None,
        help="Path to prices JSON (symbol -> last price).",
    )
    parser.add_argument(
        "--prices-json", type=str, default=None, help="Inline prices JSON."
    )
    parser.add_argument(
        "--weights",
        type=str,
        default=None,
        help="Path to target weights JSON (symbol -> weight).",
    )
    parser.add_argument(
        "--weights-json", type=str, default=None, help="Inline target weights JSON."
    )
    parser.add_argument(
        "--cash",
        type=float,
        default=0.0,
        help="Uninvested cash balance (default: 0.0).",
    )
    parser.add_argument(
        "--hold-threshold",
        type=float,
        default=DEFAULT_HOLD_THRESHOLD,
        help=f"Weight-delta threshold below which a symbol is HOLD (default: {DEFAULT_HOLD_THRESHOLD}).",
    )
    parser.add_argument(
        "--blend",
        action="store_true",
        help="Use the saved preferred blend (config/preferred_blend.json) as the "
        "target weights instead of --weights.",
    )
    parser.add_argument(
        "--from-snapshot",
        action="store_true",
        help="Load current positions and prices from results/live_positions.json "
        "(prices backfilled from the close cache), instead of --positions/--prices.",
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=None,
        help="Target-allocation mode: size the target from this much cash from "
        "zero (no current holdings), pricing each asset from the close cache. "
        "Pair with --blend for the blended target.",
    )
    parser.add_argument(
        "--strategy-slice",
        type=str,
        default=None,
        metavar="KEY",
        help="Rebalance the virtual allocation slice for strategy KEY: current "
        "holdings and cash come from the ledger (analytics/ledger.py), target "
        "weights default to the strategy's latest weights (override with "
        "--weights/--blend). Add investable cash with --budget or --cash.",
    )
    parser.add_argument(
        "--json-out",
        action="store_true",
        help="Also print the plan as JSON (machine-readable) after the table.",
    )

    args = parser.parse_args()

    # Target weights first (needed to price a from-budget target book).
    if args.blend:
        weights = blended_target_weights(load_blend())
        if not weights:
            raise SystemExit(
                "No usable preferred blend — set one in config/preferred_blend.json "
                "or on the live-risk page first."
            )
    elif args.strategy_slice and args.weights is None and args.weights_json is None:
        # Slice mode default: the strategy's own latest target weights.
        weights = latest_target_weights(args.strategy_slice)
        if not weights:
            raise SystemExit(
                f"No target weights found for slice {args.strategy_slice!r} — run "
                "its backtest first, or pass --weights/--blend."
            )
    else:
        weights = _load_dict_arg(args.weights, args.weights_json, "weights")

    if args.strategy_slice:
        # Slice mode: holdings + cash come from the ledger; price from the cache.
        ledger = load_ledger()
        positions = dict(holdings_by_strategy(ledger).get(args.strategy_slice, {}))
        slice_cash = cash_by_strategy(ledger).get(args.strategy_slice, 0.0)
        units = load_price_units()
        symbols = set(positions) | set(weights)
        prices = {sym: (close_price_base(sym, units) or 0.0) for sym in symbols}
        cash = slice_cash + (args.budget or 0.0) + args.cash
    elif args.budget is not None:
        # Target-allocation mode: build from zero cash, price from the cache.
        units = load_price_units()
        positions = {}
        prices = {sym: (close_price_base(sym, units) or 0.0) for sym in weights}
        cash = args.budget
    elif args.from_snapshot:
        positions, prices = _load_snapshot()
        cash = args.cash
    else:
        positions = _load_dict_arg(args.positions, args.positions_json, "positions")
        prices = _load_dict_arg(args.prices, args.prices_json, "prices")
        cash = args.cash

    plan = compute_rebalance_plan(
        positions=positions,
        prices=prices,
        target_weights=weights,
        cash=cash,
        hold_threshold=args.hold_threshold,
    )

    if args.strategy_slice:
        print(f"\nSlice: {args.strategy_slice}")
        print(f"Slice cash (from ledger): {slice_cash:,.2f}")
        holdings_value = plan.total_portfolio_value - cash
        print(f"Slice holdings value: {holdings_value:,.2f}")

    print_plan_table(plan)

    if args.json_out:
        print(json.dumps(plan.to_dict(), indent=2))


if __name__ == "__main__":
    main()
