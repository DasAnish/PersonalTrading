# Phase 5 — Forward-Looking Live Risk Dashboard

## Goal
Build a read-only live risk page that pulls current IB positions and computes real-time risk metrics (VaR, CVaR, correlation, concentration) and shows drift from strategy target weights.

## TODOs
- [ ] Create `scripts/server/risk.py`: blueprint with `/live-risk` route; fetches positions via `get_positions` MCP/IB client, fetches recent price history from cache for each held symbol
- [ ] Compute live risk metrics: parametric VaR (95%, 99%), historical CVaR (95%), correlation matrix of current holdings, Herfindahl-Hirschman Index for concentration
- [ ] Add drift report: compare current portfolio weights (from IB positions) vs target weights from the last saved backtest result for a user-selected strategy; highlight symbols that have drifted beyond a threshold (default ±5%)
- [ ] Write `templates/live_risk.html`: single-page dashboard with a positions table, VaR/CVaR cards, correlation heatmap (Chart.js), concentration bar chart, and drift table
- [ ] Register the risk blueprint in `scripts/server/app.py` and add nav link to the live risk page from the overview
- [ ] Graceful fallback: if IB Gateway is not connected, show cached position data (or a clear "IB offline" banner) rather than an error

## Notes
- No orders ever sent — this page is strictly read-only
- VaR computed on daily return history from the parquet cache
