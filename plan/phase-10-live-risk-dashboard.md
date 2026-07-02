# Phase 10 — Forward-Looking Live Risk Dashboard

**Model**: sonnet

## Goal
Read-only live risk page pulling current IB positions: real-time risk metrics (VaR, CVaR,
correlation, concentration) and drift from strategy target weights. (Carried over verbatim
in scope from the previous plan's Phase 5.)

## TODOs
- [ ] Create `scripts/server/risk.py`: blueprint with `/live-risk` route; fetches positions via the IB client, recent price history from the parquet cache for each held symbol
- [ ] Compute live risk metrics: parametric VaR (95%, 99%), historical CVaR (95%), correlation matrix of current holdings, Herfindahl–Hirschman Index for concentration
- [ ] Drift report: current portfolio weights (from IB positions) vs target weights from the last saved backtest result for a user-selected strategy; highlight drift beyond ±5% — reuse `analytics/rebalance.py` (Phase 5) for the delta math
- [ ] Write `templates/live_risk.html`: positions table, VaR/CVaR cards, correlation heatmap, concentration bar chart, drift table — using the Phase 4 static JS modules
- [ ] Register the risk blueprint in `scripts/server/app.py`; add nav link from the overview
- [ ] Graceful fallback: if IB Gateway is offline, render from cached position/price data with a clear "IB offline — data as of <ts>" banner rather than an error

## Validation
- `python -m pytest -m "not slow" -q` → green
- `/live-risk` renders with IB offline (fallback path exercised in this environment)
- With a cached-positions fixture: VaR/CVaR/HHI/drift values shown
- grep confirms no order-placement code paths (`placeOrder`, `bracketOrder`, etc.) anywhere in the new code
- `black --check` clean; files ≤600 lines

## Rollback
Single commit `Phase 10: live risk dashboard`.

## Notes
- No orders ever sent — this page is strictly read-only.
- VaR computed on daily return history from the parquet cache.
