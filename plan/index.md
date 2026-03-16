# Plan: DSR & PBO Overfitting Analysis

**Created**: 2026-03-16
**Status**: In Progress

## Milestones

| # | Phase | Status |
|---|-------|--------|
| 1 | [Setup & Reference Library](phase-01-setup-reference.md) | ✅ Done |
| 2 | [Core Analytics Module](phase-02-core-analytics.md) | 🔄 In Progress |
| 3 | [Extend ParameterSweep](phase-03-param-sweep.md) | ⬜ Not Started |
| 4 | [Top-Level CLI Script](phase-04-cli-script.md) | ⬜ Not Started |
| 5 | [Flask Dashboard Integration](phase-05-dashboard.md) | ⬜ Not Started |
| 6 | [Build-Strategies Skill Integration](phase-06-skill.md) | ⬜ Not Started |
| 7 | [Tests](phase-07-tests.md) | ⬜ Not Started |

## All TODOs

### Phase 1 — Setup & Reference Library
- [x] Clone pypbo reference repo
- [x] Read pypbo source (pbo.py, metrics.py)
- [x] Document key functions to adapt

### Phase 2 — Core Analytics Module
- [ ] Implement DSRResult, PBOResult, OverfittingAnalysis dataclasses
- [ ] Implement calculate_deflated_sharpe_ratio()
- [ ] Implement calculate_pbo()
- [ ] Implement run_overfitting_analysis() orchestrator
- [ ] Implement overfitting_analysis_to_dict()
- [ ] Export from analytics/__init__.py

### Phase 3 — Extend ParameterSweep
- [ ] Add store_returns flag and return_series_ dict
- [ ] Extract _run_single_combination() method
- [ ] Add get_return_matrix() method
- [ ] Verify no regression in WalkForwardAnalysis

### Phase 4 — Top-Level CLI Script
- [ ] CLI argument parsing
- [ ] Mode 1: sweep + overfitting in one pass
- [ ] Mode 2: DSR-only from existing portfolio_history.json
- [ ] resolve_strategy_class(), print_analysis_report(), save_analysis()
- [ ] Edge case handling

### Phase 5 — Flask Dashboard Integration
- [ ] load_overfitting_analysis() in data.py
- [ ] /api/strategy/<key>/overfitting endpoint in api.py
- [ ] Pass overfitting data to strategy detail template in routes.py
- [ ] Overfitting tab in strategy detail template (DSR, PBO, logit chart)

### Phase 6 — Build-Strategies Skill Integration
- [ ] Update build-strategies/SKILL.md with Step 4b
- [ ] Update build-strategies-auto/SKILL.md with Step 4b

### Phase 7 — Tests
- [ ] DSR unit tests
- [ ] PBO unit tests
- [ ] ParameterSweep with store_returns tests
- [ ] End-to-end integration test
- [ ] Serialisation test
- [ ] Full test suite (no regressions)
