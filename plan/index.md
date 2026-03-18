# Plan: Analysis Depth — Stress Testing, CPCV, Block Bootstrap, Scenario Removal, Live Risk Dashboard

**Created**: 2026-03-17
**Status**: In Progress

## Milestones

| # | Phase | Status |
|---|-------|--------|
| 1 | [Stress Testing Framework](phase-01-stress-testing.md) | ✅ Done |
| 2 | [Scenario Removal (Leave-One-Crisis-Out)](phase-02-scenario-removal.md) | ⬜ Not Started |
| 3 | [CPCV (Combinatorial Purged Cross-Validation)](phase-03-cpcv.md) | ⬜ Not Started |
| 4 | [Block Bootstrap](phase-04-block-bootstrap.md) | ⬜ Not Started |
| 5 | [Forward-Looking Live Risk Dashboard](phase-05-live-risk-dashboard.md) | ⬜ Not Started |

## All TODOs

### Phase 1 — Stress Testing Framework
- [ ] Define crisis periods as named constants in `analytics/stress_testing.py`
- [ ] Implement `StressTester` class with crisis slicing and metrics (Sharpe, max DD, recovery days, return)
- [ ] Add `--stress-test` flag to `run_backtest.py`
- [ ] Write `tests/test_stress_testing.py`
- [ ] Add "Stress Periods" tab to Flask dashboard strategy detail page
- [ ] Add stress data to strategy JSON output

### Phase 2 — Scenario Removal (Leave-One-Crisis-Out)
- [ ] Implement `run_leave_one_out()` in `analytics/stress_testing.py`
- [ ] Compute Sharpe contribution (delta) per crisis period
- [ ] Add `--scenario-removal` CLI flag
- [ ] Write tests for scenario removal
- [ ] Add "Scenario Removal" sub-section to dashboard Stress Periods tab

### Phase 3 — CPCV (Combinatorial Purged Cross-Validation)
- [ ] Implement `analytics/cpcv.py` with `CPCVEngine`
- [ ] Compute OOS Sharpe distribution and summary statistics
- [ ] Integrate with `BacktestEngine`
- [ ] Add `--method cpcv` flag to `run_overfitting.py`
- [ ] Write `tests/test_cpcv.py`
- [ ] Add CPCV results to JSON output and dashboard Overfitting tab

### Phase 4 — Block Bootstrap
- [ ] Implement `analytics/bootstrap.py` with `BlockBootstrap`
- [ ] Implement stationary block bootstrap (geometric block length)
- [ ] Run N bootstrap iterations, collect metric distributions
- [ ] Add `--method bootstrap` flag to `run_overfitting.py`
- [ ] Write `tests/test_bootstrap.py`
- [ ] Add bootstrap results to JSON output and dashboard Overfitting tab

### Phase 5 — Forward-Looking Live Risk Dashboard
- [ ] Create `scripts/server/risk.py` blueprint with `/live-risk` route
- [ ] Compute live risk metrics (VaR, CVaR, correlation, HHI)
- [ ] Add drift report (current weights vs strategy target)
- [ ] Write `templates/live_risk.html`
- [ ] Register blueprint and add nav link in `app.py`
- [ ] Graceful fallback when IB Gateway offline
