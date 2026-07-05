# Phase 13 — Validation Battery (validate_strategy.py)

**Model**: sonnet (battery + CLI) + haiku (tests)

## Goal
One-shot per-strategy validation battery: MinBTL → DSR → CPCV → block bootstrap, with a
single overall verdict, writing `results/strategies/<key>/validation.json`. Reuses Phase 6–9
analytics — no statistical logic reimplemented.

## TODOs
- [x] `analytics/validation.py` (<350 lines) —
      `run_validation_battery(strategy_key, results_dir, *, n_trials, cpcv_folds=6,
      bootstrap_n=500, block_months=3, embargo_days=10) -> ValidationResult`.
      Reuse: `calculate_minbtl` + DSR path (analytics/overfitting.py), `CPCVEngine`
      (analytics/cpcv.py), `BlockBootstrap.run_fast` (analytics/bootstrap.py),
      `load_strategy_payload` (backtesting/results_schema.py).
      Overall rule: FAIL if MinBTL history-too-short OR DSR fails OR CPCV fails;
      WARN if any test warns (bootstrap p5 Sharpe < 0 → WARN, never FAIL — fast mode only);
      else PASS. All values inf/NaN-safe (null in JSON).
- [x] `scripts/validate_strategy.py` — `--strategy` (required), `--n-trials` (default from
      `build_n_trials_map` in run_all_overfitting.py — import, don't copy), `--cpcv-folds`,
      `--bootstrap-n`, `--block-months`, `--embargo-days`, `--json` (single-line machine
      output for the analyst agent). Writes validation.json; human output = test|value|verdict
      table + overall.
- [x] `tests/test_validation.py` — battery on synthetic saved strategy (tmp results dir),
      overall-verdict rule matrix, JSON validity + inf/NaN-free

## Validation
- `pytest tests/test_validation.py` + full suite green; `black --check` clean; files ≤600 lines
- Smoke: `python scripts/validate_strategy.py --strategy hrp --json` on real results →
  valid JSON with all four test blocks + overall

## Rollback
Single commit `Phase 13: validation battery (validate_strategy.py)`.
