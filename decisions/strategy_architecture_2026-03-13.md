# Strategy Architecture Refactoring - Design Decisions

**Date:** March 13, 2026
**Decision Owner:** User Request + Claude Analysis
**Status:** Approved & Implemented

## Problem Statement

The original strategy architecture had fragmentation across multiple base classes and unclear data flow:
- BaseStrategy interface for simple weight calculation
- ExecutableStrategy hierarchy with MarketStrategy/AllocationStrategy/OverlayStrategy
- Lookback complexity scattered across engine and strategies
- Individual assets (VUSA, AAPL) not treated as strategies
- YAML definitions hard to reference and compose

## Decision: Unified Strategy Interface

### Option 1: Keep Existing Hierarchy ❌
**Rejected Because:**
- Confusing with 4+ base classes (BaseStrategy, ExecutableStrategy, MarketStrategy, etc.)
- Duplicated interfaces for same concepts
- Hard to compose strategies
- Assets not first-class citizens

### Option 2: Unified Strategy Interface ✅ SELECTED
**Rationale:**
- Single, consistent interface for all strategy types
- Everything is a Strategy (assets, portfolios, overlays)
- Enables deep composability (EqualWeight([HRP(...), TrendFollowing(...)]))
- Clear contracts via `get_data_requirements()`
- Backward incompatible but cleaner (user approved "clean break")

**Implementation:**
- Single `Strategy` ABC with 4 required methods
- Three concrete types: AssetStrategy, AllocationStrategy, OverlayStrategy
- All strategies implement same interface

## Decision: MarketData Singleton

### Option 1: Keep Distributed Data Fetching ❌
**Rejected Because:**
- Engine must calculate lookback for each strategy
- Data passing through function signatures
- Hard to reuse data across multiple strategies
- Lookback logic duplication

### Option 2: MarketData Singleton ✅ SELECTED
**Rationale:**
- Centralized data management
- Strategies never calculate lookbacks (no complexity)
- Data slicing in `get_context_for_date()` prevents lookahead bias
- Efficient data reuse across strategies
- Clear separation: singleton handles data, engine handles simulation

**Trade-offs:**
- Introduces global state (but minimal - just data)
- Async required for data fetching
- Reset needed for testing

## Decision: Asset-as-Strategy Pattern

### Option 1: Assets as Configuration ❌
**Rejected Because:**
- Assets different from strategies
- Can't use HRP(VUSA) - mixes patterns
- Meta-portfolio composition impossible

### Option 2: Assets as First-Class Strategies ✅ SELECTED
**Rationale:**
- VUSA = AssetStrategy('VUSA')
- Can be used anywhere strategies expected
- Enables: `HRP([AssetStrategy('VUSA'), AssetStrategy('SSLN')])`
- Enables: `EqualWeight([HRPStrategy(...), TrendFollowingStrategy(...)])`
- Unlocks "Everything is a Strategy" vision

**Example:**
```python
# Single asset
vusa = AssetStrategy('VUSA')

# Asset in portfolio
hrp = HRPStrategy(underlying=[vusa, ssln])

# Portfolio as asset in meta-portfolio
meta = EqualWeightStrategy(underlying=[hrp, trend])
```

## Decision: Clean Break vs Backward Compatibility

### Option 1: Full Backward Compatibility ❌
**Rejected Because:**
- Keep old base.py alongside new core.py
- Adapter classes needed
- Confuses codebase
- User explicitly chose "clean break"

### Option 2: Clean Break ✅ SELECTED (User Approved)
**Rationale:**
- Delete strategies/base.py
- Delete strategies/markets.py
- No legacy code in codebase
- Faster implementation
- User approved this approach upfront

**Impact:**
- All existing code must refactor
- No migration path
- Cleaner final codebase

## Decision: JSON vs YAML Definitions

### Option 1: Keep YAML ❌
**Considered But:**
- YAML harder to validate
- Referencing awkward in YAML
- Less tooling support

### Option 2: Switch to JSON ✅ SELECTED
**Rationale:**
- Better tooling (JSON Schema validation)
- Cleaner referencing (asset refs like "assets/vusa")
- Standard format
- Can auto-validate

**Format:**
```json
{
  "type": "asset|allocation|overlay|composed",
  "class": "ClassName",
  "name": "Display Name",
  "parameters": {...},
  "underlying": ["ref/to/other"]
}
```

## Decision: Lookback Handling

### Option 1: Engine Calculates Lookback ❌
**Rejected Because:**
- Engine must introspect strategy
- Lookback scattered across code
- TrendFollowing bug: engine sent 252 days, strategy needed 509

### Option 2: Strategy Reports Requirements ✅ SELECTED
**Rationale:**
- Strategy implements `get_data_requirements()`
- Returns lookback_days needed
- MarketData singleton fetches with lookback
- Engine gets pre-sliced StrategyContext
- No lookback math in strategy code

**Benefits:**
- Clear contract
- No surprises
- Composable (overlays add to lookback)

## Decision: Async Architecture

### Option 1: Keep Sync ❌
**Rejected Because:**
- Blocking I/O for data fetching
- Can't parallelize strategy runs

### Option 2: Go Async ✅ SELECTED
**Rationale:**
- `async def run_backtest()`
- `await mds.fetch_data()`
- Enables future parallelization
- Singleton.fetch_data() is async

## Decisions NOT Made

### Multi-Strategy Comparison
- Already supported: Run multiple strategies, compare results
- Meta-portfolios achieve this via composition

### Live Trading
- Out of scope for this refactor
- Architecture supports it (strategies provide weights)

### Parameter Optimization
- Out of scope
- Can add later as wrapper strategy

## Trade-offs Summary

| Decision | Benefit | Cost |
|----------|---------|------|
| Unified Interface | Composability | Must refactor all strategies |
| Singleton Pattern | Data efficiency | Global state, needs reset for tests |
| Asset-as-Strategy | Deep composition | Adds complexity |
| Clean Break | Clean codebase | No migration path |
| JSON Definitions | Better tooling | New format to learn |
| Async | Scalability | Must use async/await |

## Risk Mitigation

**Risk:** Engine breaking with new Strategy interface
**Mitigation:** Comprehensive unit tests (19 tests, all passing)

**Risk:** Data singleton state pollution between backtests
**Mitigation:** `MarketDataService.reset()` for testing

**Risk:** Overlays incomplete
**Mitigation:** Imports fixed, method signatures updated, remaining work documented

## Validation

✅ All imports successful
✅ 19 unit tests passing
✅ 3 core strategies refactored
✅ Architecture aligns with user vision
✅ Code committed to remote

## Future Considerations

1. **Async Strategy Execution** - `await strategy.run(engine, start, end)`
2. **Parallel Strategy Runs** - Run multiple strategies concurrently
3. **Lazy Data Loading** - Load data only when strategies request it
4. **Strategy Validation** - Validate requirements before fetching
5. **Metadata Tracking** - Track strategy parameters in results

---

**Related:**
- ai_iterations/2026-03-13_strategy_architecture_refactor.md (implementation details)
- strategies/core.py (implementation reference)
- data/market_data_service.py (singleton implementation)
