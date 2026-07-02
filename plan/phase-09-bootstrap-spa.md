# Phase 9 — Block Bootstrap + White's Reality Check / Hansen's SPA

**Model**: sonnet

## Goal
Stationary block bootstrap for robustness distributions (closes old plan Phase 4), plus
data-snooping tests (White's RC, Hansen's SPA) across the whole strategy library.
SPA reuses the bootstrap primitive — build bootstrap first, same phase.

## TODOs
- [ ] New `analytics/bootstrap.py`: `stationary_bootstrap_indices(t, expected_block, n_iter, rng) -> np.ndarray` (Politis–Romano geometric block lengths with wrap-around) as a reusable primitive; `BlockBootstrap` — resample contiguous return blocks, rebuild synthetic price series, re-run the backtest per iteration (default n=500, block_months=3 ≈ 63 trading days); collect Sharpe/Calmar/maxDD/annual-return distributions
- [ ] `--bootstrap-fast` mode: resample the realized *strategy* returns directly (no backtest re-runs) — cheap approximation used by default in tests and available on the CLI
- [ ] New `analytics/spa.py`: White's Reality Check p-value (max mean-differential statistic vs benchmark, bootstrapped via `stationary_bootstrap_indices`) and Hansen's SPA (studentized; lower/consistent/upper p-value variants). Input: (T,N) return matrix of all strategies + benchmark returns (equal_weight); reuse `build_family_return_matrix`-style assembly from `results_schema`
- [ ] CLI: `--method bootstrap --bootstrap-n 500 --block-months 3 [--bootstrap-fast]` on `run_overfitting.py`; `--spa` flag on `run_all_overfitting.py` writing `results/spa_analysis.json` plus a per-strategy `spa` stub (p-values + rank) in each `overfitting_analysis.json`
- [ ] Dashboard: bootstrap Sharpe histogram with a vertical line at the realized Sharpe; SPA p-value row on the Overfitting tab
- [ ] New `tests/test_bootstrap.py`: seeded determinism; mean block length ≈ expected_block; synthetic series length preserved; distribution shape. SPA power test: 1 true-alpha + 19 noise strategies rejects the null; all-noise does not (seeded). Full-re-run bootstrap tests marked `@pytest.mark.slow`
- [ ] Refresh `docs/overfitting.md`: all new methods (MinBTL, purged k-fold, walk-forward, CPCV, bootstrap, SPA), flags, verdict tables, and updated output schema

## Validation
- `python -m pytest -m "not slow" -q` → green; run the slow bootstrap suite once (`-m slow`)
- `python scripts/run_overfitting.py --strategy hrp_single --method bootstrap --bootstrap-fast` writes the bootstrap section
- `python scripts/run_all_overfitting.py --spa` writes results/spa_analysis.json
- Dashboard renders bootstrap histogram + SPA row
- `black --check` clean; files ≤600 lines

## Rollback
Single commit `Phase 9: block bootstrap + SPA`.
