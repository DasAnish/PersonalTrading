# Phase 2 — Add Strategies Overview Page

## Goal
Add a new `/` overview page listing all strategies with key metrics, and rename the current single-strategy detail page to `/strategy/<key>` (or keep it at `/` with a different tab name).

## TODOs
- [x] Design the new overview page: table of all strategies with columns (Name, Sharpe, CAGR, Max Drawdown, Volatility)
- [x] Add `GET /` route for the new overview page
- [x] Move current strategy detail view to `GET /strategy/<key>` (or make it accessible from the overview)
- [x] Add navigation link from overview to strategy detail and back
- [x] Rename the "Overview" tab in the strategy detail view to "Strategy Overview"
- [x] Wire up overview page: clicking a strategy row navigates to its detail view
- [x] Add auto-refresh: overview page polls `/api/strategies/summary` every 10 seconds; detail page re-fetches strategy data every 10 seconds

## Notes
