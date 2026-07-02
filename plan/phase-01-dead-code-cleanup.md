# Phase 1 — Dead-Code Cleanup

**Model**: haiku

## Goal
Remove verified-dead modules, functions, and a broken test file. Zero behavior change.

## Verified facts (from scan)
- `strategies/models.py` (81 lines): every class self-labeled DEPRECATED; zero importers anywhere.
- `_run_strategy` (`scripts/run_backtest.py:572–620`): zero callers; calls `engine.run_backtest_with_overlay(...)` which does not exist on `BacktestEngine` — would crash if ever called. Contains the file's only `strategies.base` import (line 589, function-local).
- `strategies/base.py` (29 lines): pure alias shim over `strategies.core` (`ExecutableStrategy = Strategy`, `MarketStrategy = AssetStrategy`, ...). Importers: `strategies/strategy_loader.py:29` (real), run_backtest.py:589 (inside dead func), `tests/test_strategies.py:14` (broken — imports `BaseStrategy` which does not exist in base.py).
- `tests/test_strategies.py` (431 lines): tests the pre-refactor API (`BaseStrategy`, `calculate_weights(prices)` signature); fails at pytest collection. Current-architecture coverage lives in `tests/test_core_architecture.py` and `tests/test_backtest_e2e.py`.

## TODOs
- [x] Delete dead `_run_strategy` function from `scripts/run_backtest.py` (lines ~572–620)
- [x] Rewire `strategies/strategy_loader.py:29` to `from strategies.core import Strategy as ExecutableStrategy, AssetStrategy as MarketStrategy, AllocationStrategy, OverlayStrategy` (keep alias names — no internal renames in the loader)
- [x] Delete `tests/test_strategies.py` (first skim for unique behavioral assertions worth porting to `tests/test_core_architecture.py`; most are already covered)
- [x] Delete `strategies/base.py` and `strategies/models.py`
- [x] Run Black on touched files

## Validation
- `grep -rn "strategies.base\|strategies.models" --include="*.py" .` → no matches
- `python -c "from strategies.strategy_loader import StrategyLoader"` → succeeds
- `python -m pytest -m "not slow" -q` → collection error gone; 239 passed / 4 failed (same 4 IB-connection failures as baseline, no new failures)
- `black --check` clean on touched files

## Rollback
Single commit `Phase 1: dead-code cleanup`; revert if anything downstream breaks.

## Notes
- `scripts/run_hrp_backtest.py` and `scripts/test_hrp_backtest.py` are legacy candidates for a future deletion pass — do NOT touch in this phase.
