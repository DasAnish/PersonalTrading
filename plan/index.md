# Plan: Refactor Flask Server + Overview Page + Project Structure Doc

**Created**: 2026-03-16
**Status**: Complete

## Milestones

| # | Phase | Status |
|---|-------|--------|
| 1 | [Split Flask Server into Modules](phase-01-split-server.md) | ✅ Done |
| 2 | [Add Strategies Overview Page](phase-02-overview-page.md) | ✅ Done |
| 3 | [Create project-structure.md](phase-03-project-structure-doc.md) | ✅ Done |

## All TODOs

### Phase 1 — Split Flask Server into Modules
- [ ] Create `scripts/server/` package with `__init__.py`
- [ ] Extract data loading functions into `scripts/server/data.py`
- [ ] Extract API endpoints into `scripts/server/api.py`
- [ ] Extract page routes + HTML templates into `scripts/server/routes.py`
- [ ] Create `scripts/server/app.py` as the Flask app factory
- [ ] Update `scripts/serve_results.py` to be a thin entry point that imports from the package
- [ ] Verify the server still starts and all routes work

### Phase 2 — Add Strategies Overview Page
- [ ] Design the new overview page: table of all strategies with columns (Name, Sharpe, CAGR, Max Drawdown, Volatility)
- [ ] Add `GET /` route for the new overview page
- [ ] Move current strategy detail view to `GET /strategy/<key>` (or make it accessible from the overview)
- [ ] Add navigation link from overview to strategy detail and back
- [ ] Rename the "Overview" tab in the strategy detail view to "Strategy Overview"
- [ ] Wire up overview page: clicking a strategy row navigates to its detail view
- [ ] Add auto-refresh: overview page polls `/api/strategies/summary` every 10 seconds; detail page re-fetches strategy data every 10 seconds

### Phase 3 — Create project-structure.md
- [ ] Glob all files in the project (excluding .git, __pycache__, results/, data/cache/)
- [ ] Write `docs/project-structure.md` with annotated tree and per-file descriptions
- [ ] Update `CLAUDE.md` documentation table to include project-structure.md
