# Plan: Cleanup, Modularity, Reporting & Overfitting Extension

**Created**: 2026-07-02
**Status**: In Progress

Supersedes the previous "Analysis Depth" plan (2026-03-17). Its Phase 1 (Stress Testing) shipped;
its Phases 2–4 (Scenario Removal, CPCV, Block Bootstrap) are absorbed into Phases 7–9 below;
its Phase 5 (Live Risk Dashboard) is carried over as Phase 10.

Execution: each phase is implemented by a subagent (model per table), validated by the
orchestrator (pytest baseline + phase acceptance checks + black + 600-line rule), then
committed as a single commit on `claude/assess-project-state-Bsig4`.

Baseline (2026-07-02): 239 passed, 4 failed (IB-connection tests — no gateway in env, expected),
`tests/test_strategies.py` fails at collection (fixed in Phase 1).

## Milestones

| # | Phase | Model | Status |
|---|-------|-------|--------|
| 1 | [Dead-Code Cleanup](phase-01-dead-code-cleanup.md) | haiku | ⬜ Not Started |
| 2 | [Critical Bug Fixes](phase-02-critical-bug-fixes.md) | sonnet | ⬜ Not Started |
| 3 | [Runner Extraction + Results Schema](phase-03-runner-and-results-schema.md) | sonnet | ⬜ Not Started |
| 4 | [Metrics Dedup, Splitters, Frontend Modules](phase-04-metrics-splitters-frontend.md) | sonnet | ⬜ Not Started |
| 5 | [Reporting](phase-05-reporting.md) | sonnet | ⬜ Not Started |
| 6 | [Overfitting Foundations](phase-06-overfitting-foundations.md) | sonnet | ⬜ Not Started |
| 7 | [Scenario Removal Completion](phase-07-scenario-removal.md) | sonnet | ⬜ Not Started |
| 8 | [CPCV](phase-08-cpcv.md) | sonnet | ⬜ Not Started |
| 9 | [Block Bootstrap + SPA / Reality Check](phase-09-bootstrap-spa.md) | sonnet | ⬜ Not Started |
| 10 | [Live Risk Dashboard](phase-10-live-risk-dashboard.md) | sonnet | ✅ Complete |

Phases 1–10 landed 2026-07-02/03 (commits through b2c9096), pushed to `main`.

## Extension: Research Ingestion + Validation Battery (added 2026-07-05)

Opens the closed strategy-sourcing loop: external research inflow with pre-registered
hypotheses, mechanism-diversity steering, and the Phase 6–9 statistical battery as the
per-candidate gate in `/build-strategies`. Out-of-universe holdout testing deferred.

| # | Phase | Model | Status |
|---|-------|-------|--------|
| 11 | [Research Infrastructure](phase-11-research-infrastructure.md) | sonnet | ✅ Complete |
| 12 | [Mechanism Taxonomy + Coverage](phase-12-mechanism-taxonomy.md) | sonnet+haiku | ✅ Complete |
| 13 | [Validation Battery](phase-13-validation-battery.md) | sonnet+haiku | ⬜ Not Started |
| 14 | [Pipeline Wiring + Dashboard](phase-14-pipeline-wiring.md) | sonnet+haiku | ⬜ Not Started |

## Dependency order

1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10.
Phase 3's runner gates 7/8/9; Phase 4's splitters gate 6/8; Phase 5's rebalance module is reused by 10.
Extension: 11 and 12 are independent of each other; 13 depends on 6/8/9 (landed); 14 depends on 11+12+13.

## Cross-phase constraints

- `mcp_server/server.py:340` shells out to `scripts/run_backtest.py --all` — never rename existing CLI flags.
- All touched Python files ≤600 lines; Black, line length 88; type hints.
- NEVER place/submit/modify IB orders — research only.
- One commit per phase; `git revert` a phase's commit if its validation regresses later.
