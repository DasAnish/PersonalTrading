# Phase 5 — Reporting

**Model**: sonnet (docs sync sub-task may go to haiku)

## Goal
Persisted human-readable reports per strategy, close the dashboard's k-fold rendering gap,
and back the rebalance skill with tested Python instead of LLM arithmetic.

## TODOs
- [ ] New `analytics/report.py`: `build_report(strategy_key, results_dir) -> str` producing markdown via `results_schema` loaders — header/config, metrics table, stress-test crisis table + scenario-removal deltas with verdicts, overfitting DSR/PBO/k-fold verdict cards; tolerate missing stress/overfitting files gracefully (section omitted with a note). Optional `to_html(md) -> str` for a self-contained HTML variant (inline CSS, no JS)
- [ ] Write reports to `results/strategies/<key>/report.md`; add `--report` flag to `scripts/run_backtest.py` (generate after save)
- [ ] New `scripts/generate_report.py --strategy <key> | --all` so reports can be regenerated without re-running backtests
- [ ] Dashboard: render `kfold` section in strategy.html Overfitting tab — `fold_sharpes` bar chart, `fraction_positive`, verdict badge (data exists in overfitting_analysis.json, currently never rendered)
- [ ] Sync `docs/dashboard.md` with the real endpoint list (overfitting, stress_test, compare, rolling, monthly, export)
- [ ] New `analytics/rebalance.py`: pure `compute_rebalance_plan(positions: dict, prices: dict, target_weights: dict, cash: float) -> RebalancePlan` dataclass — per-symbol current weight, target weight, delta weight, delta value, estimated shares, direction, totals. NO IB imports, NO side effects, NO order code. Small `__main__` entry taking JSON file paths. Update `.claude/skills/rebalance/SKILL.md` to call it; keep the manual-orders warning verbatim
- [ ] New tests: `tests/test_report.py` (fixture result dirs in tmp_path; full report; missing stress/overfitting files don't crash), `tests/test_rebalance.py` (weights sum, zero-delta, symbol on one side only, zero-price guard)

## Validation
- `python -m pytest -m "not slow" -q` → green
- `python scripts/generate_report.py --strategy <key>` emits report.md containing all sections present in that strategy's JSON
- Dashboard shows the k-fold card on a strategy with overfitting results
- `black --check` clean; files ≤600 lines

## Rollback
Single commit `Phase 5: reporting`.
