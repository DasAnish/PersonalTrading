---
name: rebalance
description: Generate a rebalance report comparing current IB portfolio positions against strategy target allocations
disable-model-invocation: true
argument-hint: <strategy>
---

> **IMPORTANT: NEVER send orders into IB Gateway.** This skill only generates a report. The user enters all orders manually. Never place, submit, modify, or cancel any trade orders programmatically.

Generate a rebalance report for the specified strategy. Available strategies: hrp, trend_following, equal_weight, minimum_variance, risk_parity, momentum.

If an argument is provided, use it as the strategy name; otherwise default to `hrp`.

1. Fetch current portfolio positions using the `mcp__ib-trading__get_positions` tool
2. Fetch the latest backtest results for the strategy using the `mcp__ib-trading__get_backtest_results` tool to get the most recent target weights
3. Calculate the delta between current holdings and target allocations (current weight % vs target weight %)
4. Generate Rebalance Report based on current portfolio, showing:
   - Current positions (ticker, shares, market value, current weight %)
   - Target weights from the strategy (ticker, target weight %)
   - Required trades (ticker, direction BUY/SELL, delta weight %, estimated shares to trade)
   - Total portfolio value and any cash balance
   - Note reminding the user to enter all orders manually in IB Gateway
