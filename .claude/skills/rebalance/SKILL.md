---
name: rebalance
description: Generate a rebalance report comparing current IB portfolio positions against strategy target allocations
disable-model-invocation: true
argument-hint: <strategy>
---

> **IMPORTANT: NEVER send orders into IB Gateway.** This skill only generates a report. The user enters all orders manually. Never place, submit, modify, or cancel any trade orders programmatically.

Generate a rebalance report for the specified strategy. Available strategies: hrp, trend_following, equal_weight, minimum_variance, risk_parity, momentum.

If an argument is provided, use it as the strategy name; otherwise default to `hrp`.

The delta/turnover arithmetic below MUST be computed by
`scripts/rebalance_report.py` (backed by the tested, pure function
`analytics.rebalance.compute_rebalance_plan`) — do NOT compute weight
deltas, target values, or estimated share counts yourself in-model. That
computation is unit-tested (`tests/test_rebalance.py`) precisely so the
numbers in this report are reproducible instead of re-derived by the LLM
on every run.

1. Fetch current portfolio positions using the `mcp__ib-trading__get_positions` tool.
   From the returned list, build a positions JSON (`symbol -> position`)
   and a prices JSON (`symbol -> market_price`).
2. Fetch the account cash balance using the `mcp__ib-trading__get_account_summary` tool.
3. Get the strategy's most recent target weights by reading the **last row**
   of `results/strategies/<strategy_key>/weights_history.json` directly
   (via the Read tool) — `mcp__ib-trading__get_backtest_results` does not
   currently expose weights, only metrics/info/portfolio summary. Build a
   weights JSON (`symbol -> target_weight`) from that last row.
4. Write the three JSON payloads to scratch files (e.g. under a temp/scratch
   directory) and run:
   ```
   python scripts/rebalance_report.py \
       --positions <positions.json> --prices <prices.json> \
       --weights <weights.json> --cash <cash_balance>
   ```
   This prints a table with, per symbol: current weight %, target weight %,
   delta weight %, current/target value, delta value, estimated shares,
   and direction (BUY/SELL/HOLD) — plus total portfolio value, total
   turnover, and any normalization/skip notes. It does not place any order.
5. Present that table's output as the Rebalance Report to the user, including:
   - Current positions (ticker, shares, market value, current weight %)
   - Target weights from the strategy (ticker, target weight %)
   - Required trades (ticker, direction BUY/SELL/HOLD, delta weight %, estimated shares to trade)
   - Total portfolio value and cash balance
   - Any notes from the script (e.g. weights normalized, symbol skipped for missing price)
   - A note reminding the user to enter all orders manually in IB Gateway
