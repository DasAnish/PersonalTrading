# Session Log

## Current Status (2026-03-17)

**Status**: All phases complete. No outstanding tasks.

### Completed (2026-03-17)
- Added `ProtectiveAssetAllocationStrategy` (`strategies/protective_asset_allocation.py`)
- Added `VolatilityMomentumStrategy` (`strategies/volatility_momentum.py`) with `top_n` parameter
- Strategy tags system added (`add_strategy_tags.py`) with search/filter UI on the overview dashboard page
- k-fold temporal stability analysis added to `analytics/overfitting.py`
- Batch overfitting runner `run_all_overfitting.py` for all 80+ strategy definitions
- `/build-strategies` redesigned as a persistent 4-agent team pipeline (`.claude/commands/build-strategies.md`)
- `/build-strategies-auto` added as unattended single-agent variant

### Completed (2026-03-16 — DSR/PBO Overfitting Plan, all 7 phases)
- DSR (Deflated Sharpe Ratio) and PBO (Probability of Backtest Overfitting) analytics module (`analytics/overfitting.py`)
- ParameterSweep extended to track per-trial return series for DSR/PBO input
- Walk-forward validation support
- Flask dashboard: overfitting tab with DSR/PBO scores per strategy
- `build-strategies` skill integration: auto-computes DSR/PBO after each new strategy
- Full test suite added (all passing, no regressions)

### Completed (2026-03-15)
- Fixed `/optimize` skill: now correctly passes `--strategy` flag to CLI
- Multi-strategy comparison (3+ strategies) in dashboard:
  - Replaced 2-dropdown UI with dynamic "add strategy" row system (+ Add Strategy / × remove)
  - All chart/metrics functions now loop over N strategies with a 6-color palette
  - Rolling Metrics tab supports N strategies in parallel
  - New `/api/compare?strategies=k1,k2,k3` endpoint: pairwise tracking error, info ratio, correlation matrix
- Integration tests for optimization engine (12 tests, all passing):
  - ParameterSweep: single param, multi-param, all metrics present, empty grid, insufficient data, sortino target
  - WalkForwardAnalysis: runs, produces windows, overfitting ratio, summary_df columns, raises on short data, avg metrics
- Async market data fetching in `MarketDataService.fetch_data()`:
  - Symbols now fetched concurrently with `asyncio.gather` instead of sequential loop
  - Fixed deprecated `fillna(method='ffill')` → `ffill()`

### Previously Completed
- Phase 1 (Strategies): MinimumVarianceStrategy, RiskParityStrategy, MomentumTopNStrategy + YAML definitions
- Phase 2 (Analytics): Sortino, Calmar, Information Ratio, Tracking Error, VaR/CVaR, Max DD Duration, Monthly Returns, Rolling Metrics
- Phase 3 (Optimization): ParameterSweep + WalkForwardAnalysis engines + CLI script + /optimize slash command
- Phase 4 (Dashboard): Monthly Returns Heatmap, Rolling Metrics tab, CSV export, comparison API
- Unified Strategy interface (Strategy ABC) with StrategyContext and DataRequirements
- AssetStrategy, AllocationStrategy, OverlayStrategy
- HRP, TrendFollowing, EqualWeight, JSON strategy definitions
- Overlays: VolTarget, Constraint, Leverage
- MarketDataService singleton
- Backtesting Engine with overlay support
- Data caching with --refresh flag
- All-Strategies execution mode

---

## Next Actions

- No outstanding actions. Live order execution is intentionally out of scope.

---

## Known Issues

### Trend Following Bug (FIXED)

**Problem**: Strategy always returned equal-weight allocation.

**Root cause**: BacktestEngine default `lookback_days=252` was less than TrendFollowing's required 504+5 days, triggering the equal-weight fallback on every rebalance.

**Fix**: `backtesting/engine.py` now auto-detects `strategy.lookback_days` and `strategy.smooth_window` and passes the correct total window.

Secondary fix: `_smooth_signals()` in `strategies/trend_following.py` no longer applies rolling window to cross-sectional series (would produce all-NaN for 4 assets with window=5).

**Verification**:
```
Trend Following: VUSA 35.28%, SSLN 64.72%, SGLN 0%, IWRD 0%
Equal Weight:    all 25%
Max difference: 39.72%  ✅
```

---

## Architecture Decisions

See `decisions/strategy_architecture_2026-03-13.md` for rationale behind the unified strategy interface.
