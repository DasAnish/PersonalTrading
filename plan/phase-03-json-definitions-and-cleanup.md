# Phase 3 — JSON Definitions + Remove YAML

## Goal
Create JSON definition files for every strategy that currently only exists as YAML, then delete all YAML files from `strategy_definitions/`.

## Strategies needing new JSON files

### Allocations (have YAML, need JSON)
- `hrp_ward` — HRPStrategy, linkage_method=ward
- `trend_following` — TrendFollowingStrategy, lookback=504, hl=60, smooth=5, threshold=0.1
- `minimum_variance` — MinimumVarianceStrategy
- `risk_parity` — RiskParityStrategy
- `momentum_top2` — MomentumTopNStrategy, n=2

### Composed (have YAML, need JSON)
- `hrp_with_constraints` — HRPStrategy(ward) → ConstraintStrategy(min=0.10, max=0.30)
- `trend_with_vol_12` — TrendFollowingStrategy → VolatilityTargetStrategy(target_vol=0.12)
- `trend_constrained_vol_target` — TrendFollowingStrategy → ConstraintStrategy(min=0.05, max=0.40) → VolatilityTargetStrategy(target_vol=0.12)

### Markets (have YAML — replace with asset refs in allocation files, no separate market JSON needed)
- `markets/uk_etfs.yaml` — replaced by `"underlying": ["assets/vusa", ...]` pattern
- `markets/us_equities.yaml` — same

### Overlays (have YAML, need to verify if standalone overlay JSONs are needed or only used inline)
- `constraints_5_40`, `constraints_10_30`, `vol_target_12pct`, `vol_target_15pct`, `leverage_1x` — currently exist as JSON, verify they match the schema

## TODOs
- [x] Create `strategy_definitions/allocations/hrp_ward.json`
- [x] Create `strategy_definitions/allocations/trend_following.json`
- [x] Create `strategy_definitions/allocations/minimum_variance.json`
- [x] Create `strategy_definitions/allocations/risk_parity.json`
- [x] Create `strategy_definitions/allocations/momentum_top2.json`
- [x] Create `strategy_definitions/composed/hrp_with_constraints.json` (inline nested format)
- [x] Create `strategy_definitions/composed/trend_with_vol_12.json` (inline nested format)
- [x] Create `strategy_definitions/composed/trend_constrained_vol_target.json` (double-nested)
- [x] Verify loader discovers and builds all new files correctly
- [x] Delete all `*.yaml` files from `strategy_definitions/`

## Notes
