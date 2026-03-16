# Strategies Reference

## Unified Strategy Architecture

All strategies implement the same interface enabling deep composability. Three types:

1. **AssetStrategy** - Single instrument (e.g. VUSA). Returns 100% weight to itself.
2. **AllocationStrategy** - Calculates weights across `List[Strategy]` (HRP, TrendFollowing, EqualWeight)
3. **OverlayStrategy** - Transforms weights from underlying strategy (VolTarget, Constraint, Leverage)

Core files: `strategies/core.py`, `strategies/__init__.py`

---

## Available Strategies

| Strategy | File | Key Parameter |
|----------|------|---------------|
| HRP | `strategies/hrp.py` | `linkage_method` (single\|complete\|average\|ward) |
| Trend Following | `strategies/trend_following.py` | `lookback_days=504`, `half_life_days=60` |
| Equal Weight | `strategies/equal_weight.py` | — |
| Minimum Variance | `strategies/minimum_variance.py` | lookback 252d, scipy SLSQP |
| Risk Parity | `strategies/risk_parity.py` | equal marginal risk contribution |
| Momentum Top-N | `strategies/momentum.py` | `top_n=2`, `lookback_days=252` |

**Overlays**: `VolatilityTargetStrategy`, `ConstraintStrategy`, `LeverageStrategy` — see `strategies/overlays.py`

---

## HRP Algorithm

Three-stage process:
1. **Tree Clustering** — correlation → distance matrix → `scipy linkage()`
2. **Quasi-Diagonalization** — `get_quasi_diag()` reorders so similar assets are adjacent
3. **Recursive Bisection** — `get_rec_bipart()` allocates inversely to cluster variance

Reference: De Prado (2016), "Building Diversified Portfolios that Outperform Out of Sample"
Notebook: `references/Hierarchical-Risk-Parity/Hierarchical Clustering.ipynb`

---

## Trend Following Algorithm

1. EWMA momentum over 504-day lookback (60-day half-life), annualised
2. Normalize by volatility (Sharpe-like signal)
3. Apply 5-day smoothing
4. Zero out signals with |value| < 0.1
5. Risk-parity weight by `signal / volatility` among positive signals (long-only)

> **Note**: BacktestEngine auto-detects `strategy.lookback_days` and `strategy.smooth_window` to pass the correct data window.

---

## Strategy Registry

Registered in `strategies/__init__.py`:
```python
STRATEGY_REGISTRY = {
    'hrp': {'class': HRPStrategy, ...},
    'trend_following': {'class': TrendFollowingStrategy, ...},
    'equal_weight': {'class': EqualWeightStrategy, ...},
    # + minimum_variance, risk_parity, momentum
}
```

To add a new strategy:
1. Inherit from `AllocationStrategy` or `OverlayStrategy`
2. Implement `calculate_weights(context: StrategyContext)`
3. Implement `get_strategy_lookback()`
4. Add a JSON file to `strategy_definitions/` (see JSON Strategy Definitions below)

---

## Composability Example

```python
from strategies import (
    AssetStrategy, HRPStrategy, TrendFollowingStrategy,
    VolatilityTargetStrategy, ConstraintStrategy, EqualWeightStrategy
)

assets = [AssetStrategy(s, currency='GBP') for s in ['VUSA','SSLN','SGLN','IWRD']]

hrp = HRPStrategy(underlying=assets, linkage_method='ward')
trend = TrendFollowingStrategy(underlying=assets, lookback_days=504)

# Apply overlays
hrp_30vol = VolatilityTargetStrategy(underlying=hrp, target_vol=0.30)
trend_constrained = ConstraintStrategy(underlying=trend, min_weight=0.05, max_weight=0.40)

# Meta-portfolio
meta = EqualWeightStrategy(underlying=[hrp_30vol, trend_constrained])
```

---

## JSON Strategy Definitions

Stored in `strategy_definitions/` (JSON only — no YAML):
- `assets/` — vusa, ssln, sgln, iwrd
- `allocations/` — equal_weight, hrp_single, hrp_ward, trend_following, minimum_variance, risk_parity, momentum_top2
- `overlays/` — vol_target_12/15/30pct, constraints_5_40/10_30, leverage_1x
- `composed/` — hrp_15/30vol, trend_15/30vol, hrp_with_constraints, trend_with_vol_12, trend_constrained_vol_target
- `portfolios/` — meta_trend_hrp_15/30vol, meta_multi_volatility

**Schema**: allocation and composed definitions use `"underlying"` to specify assets inline — no separate market files needed.

Custom strategy example (`strategy_definitions/allocations/my_momentum.json`):
```json
{
  "type": "allocation",
  "class": "TrendFollowingStrategy",
  "name": "My Momentum",
  "description": "Custom trend following with shorter lookback",
  "parameters": {
    "lookback_days": 252,
    "half_life_days": 30,
    "smooth_window": 3,
    "signal_threshold": 0.15
  },
  "underlying": ["assets/vusa", "assets/ssln", "assets/sgln", "assets/iwrd"]
}
```

List all available:
```bash
python -c "from strategies.strategy_loader import StrategyLoader; \
  loader = StrategyLoader(); \
  print(list(loader.list_strategies('allocation').keys()))"
```
