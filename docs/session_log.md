# Session Log

## Current Status (2026-03-13)

**Status**: 3 of 4 phases complete. Phase 3 (optimization) partially done.

### Completed This Session
- Phase 1 (Strategies): MinimumVarianceStrategy, RiskParityStrategy, MomentumTopNStrategy + YAML definitions
- Phase 2 (Analytics): Sortino, Calmar, Information Ratio, Tracking Error, VaR/CVaR, Max DD Duration, Monthly Returns, Rolling Metrics
- Phase 4 (Dashboard): Monthly Returns Heatmap, Rolling Metrics tab, CSV export, comparison API
- Phase 3 (Optimization): ParameterSweep + WalkForwardAnalysis engines + CLI script — missing: /optimize slash command

### Previously Completed
- Unified Strategy interface (Strategy ABC) with StrategyContext and DataRequirements
- AssetStrategy, AllocationStrategy, OverlayStrategy
- HRP, TrendFollowing, EqualWeight, JSON strategy definitions
- Overlays: VolTarget, Constraint, Leverage
- MarketDataService singleton
- Backtesting Engine with overlay support
- Data caching with --refresh flag
- All-Strategies execution mode
- Interactive web dashboard with strategy picker

---

## Next Actions

- [ ] Finish /optimize slash command
- [ ] Integration test optimization engine with real cached data
- [ ] Add async market data fetching to BacktestEngine
- [ ] Multi-strategy comparison (3+ strategies in dashboard)
- [ ] Live trading execution with overlay strategies

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
