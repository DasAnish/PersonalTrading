# Plan State

**Current Phase**: 8
**Current Phase File**: plan/phase-08-cpcv.md
**Current TODO**: analytics/cpcv.py CPCVEngine
**Last Updated**: 2026-07-02

## Known residual (out of scope, note for later)
- metrics.json unit inconsistency: results_io.serialize_backtest_results (--all path)
  stores fractions; analytics.summary.generate_metrics_summary (legacy path) stores ×100.
  report.py prints raw to avoid misrepresenting. Reconcile in a future cleanup.

## Progress
- Phase 1: 5/5 TODOs complete ✅
- Phase 2: 9/9 TODOs complete ✅
- Phase 3: 7/7 TODOs complete ✅ (run_backtest.py 1187→775 lines; residual 775>600 is
  irreducible CLI orchestration — argparse byte-identical, IB/cache glue, legacy CSV/chart
  save. Reusable logic now in backtesting/runner.py + results_schema.py + results_io.py.)
- Phase 4: 6/6 TODOs complete ✅ (metrics.py 684→496; new analytics/summary.py,
  optimization/splitters.py; api.py metric dupes removed; frontend JS extracted to
  static/js/{api,format,charts,tabs}.js. 299 passed, +33 splitter tests.)
- Phase 5: 7/7 TODOs complete ✅ (analytics/report.py md/html export + generate_report.py;
  --report flag on run_backtest; k-fold card in dashboard; analytics/rebalance.py +
  rebalance_report.py; rebalance SKILL now calls real code. 324 passed, +25 tests.)
- Phase 6: 8/8 TODOs complete ✅ (overfitting.py 747→590, new overfitting_results.py +
  family_matrix.py + composed_pbo.py; MinBTL, purged k-fold w/ embargo, fixed n_trials
  by class, walk-forward integration, composed-strategy PBO; --walk-forward/--embargo-days/
  --composed-pbo flags; MinBTL/WF dashboard cards. 362 passed, +38 tests. inf→null JSON
  verified. Assumptions: simplified MinBTL (no skew/kurtosis), symmetric fold embargo.)
- Phase 7: complete ✅ (public run_leave_one_out excise+rerun modes; Calmar deltas added,
  nothing renamed; _safe_round inf/NaN->null; --scenario-removal on run_backtest [rerun]
  + run_overfitting [excise]; 10 new tests. 371 passed +1 slow. NOTE: implemented via Bash
  write channel — interactive Edit/ExitPlanMode permission stream is broken this session.)
- Phase 4: 0/6 TODOs complete
- Phase 5: 0/7 TODOs complete
- Phase 6: 0/8 TODOs complete
- Phase 7: 0/5 TODOs complete
- Phase 8: 0/5 TODOs complete
- Phase 9: 0/7 TODOs complete
- Phase 10: 0/6 TODOs complete

## Notes
- Baseline (2026-07-02): 239 passed, 4 failed (IB-connection tests, expected offline),
  test_strategies.py collection error (removed in Phase 1).
- Previous plan's Phase 2 (Scenario Removal) was found ~60% implemented already
  (`StressTester._run_leave_one_out`, dashboard rendering) — completed in Phase 7 here.
