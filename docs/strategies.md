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
| Dual Momentum | `strategies/dual_momentum.py` | absolute + relative momentum |
| Mean Reversion | `strategies/mean_reversion.py` | z-score based allocation |
| Adaptive Asset Allocation | `strategies/adaptive_asset_allocation.py` | momentum + min-var hybrid |
| Protective Asset Allocation | `strategies/protective_asset_allocation.py` | defensive/protective allocation |
| Volatility Momentum | `strategies/volatility_momentum.py` | vol-adjusted momentum, `top_n=2` |
| Skewness Weighted | `strategies/skewness_weighted.py` | penalises negative skew |
| Trend + MVO | `strategies/trend_signal_mvo.py` | trend signals into mean-variance |
| Trend + Risk Parity | `strategies/trend_signal_rp.py` | trend signals into risk parity |
| Meta Portfolio | `strategies/meta_portfolio.py` | combines multiple strategies |
| Cross-Asset Carry | `strategies/cross_asset_carry.py` | carry-proxy ranking, `top_n=4` |
| Gold Safe-Haven Overlay | `strategies/gold_safe_haven_overlay.py` | drawdown-triggered gold tilt |
| Low-Beta Defensive Tilt | `strategies/low_beta_defensive_tilt.py` | bottom-N beta vs IWRD, `bottom_n=5` |
| Halloween Seasonality | `strategies/halloween_seasonality.py` | Nov–Apr equities / May–Oct defensive (validation: rejected) |

**Overlays**: `VolatilityTargetStrategy`, `ConstraintStrategy`, `LeverageStrategy` — see `strategies/overlays.py`

---

## Mechanism Taxonomy

Every strategy is tagged with its underlying economic mechanism from a fixed
10-category vocabulary. This enables systematic coverage measurement and
guides diversification of new ideas away from over-mined clusters.

| Mechanism | Classes | Use |
|-----------|---------|-----|
| **trend** | TrendFollowingStrategy, TrendSignalMVOStrategy, TrendSignalRPStrategy, DualMomentumStrategy | Price momentum; buy uptrends, sell downtrends |
| **momentum-cs** | MomentumTopNStrategy, VolatilityMomentumStrategy | Cross-sectional momentum; rank and overweight relative winners |
| **mean-reversion** | MeanReversionStrategy | Contrarian; profit from temporary dislocations |
| **carry** | CarryTiltStrategy | Return generation from interest-rate or volatility spread harvesting |
| **vol-premium** | SkewnessWeightedStrategy, LowBetaTiltStrategy | Harvest volatility premium; penalise negative skew / high beta |
| **diversification** | HRPStrategy, EqualWeightStrategy, MinimumVarianceStrategy, RiskParityStrategy | Risk reduction through decorrelation and diversification |
| **regime** | AdaptiveAssetAllocationStrategy, ProtectiveAssetAllocationStrategy | Adapt allocations to market regimes (risk-on/risk-off) |
| **hedging-overlay** | VolatilityTargetStrategy, ConstraintStrategy, LeverageStrategy, GoldSafeHavenOverlayStrategy | Modify another strategy's risk/return; stress-triggered hedges |
| **seasonality** | *(none yet)* | Exploit recurring patterns (calendar, seasonal) |
| **meta** | MetaPortfolioStrategy | Combine multiple strategies (portfolio definitions) |

### Classification Rules

**Allocations** (type = `"allocation"`): mapped to a single mechanism by their
class name (see `strategies/taxonomy.py::_ALLOCATION_CLASS_TO_MECHANISM`).

**Composed** (type = `"composed"`): inherit the mechanism of their wrapped
`underlying` strategy, but *override* when wrapped by an overlay
(e.g., `TrendFollowingStrategy` + `VolatilityTargetStrategy` → `hedging-overlay`).

**Portfolios** (type = `"portfolio"`): always `meta`.

### Tagging and Discovery

Strategy definitions can store mechanism tags in a `tags` array (each tag
formatted as `"mech:<mechanism>"`, e.g. `"mech:trend"`). Tags are auto-populated
via `scripts/tag_mechanisms.py`:

```bash
# Scan all definitions and tag with inferred mechanisms
python scripts/tag_mechanisms.py --coverage

# Show counts per mechanism
python scripts/tag_mechanisms.py --coverage --dry-run
```

Mechanisms are used by `/build-strategies` strategist stage to steer ideation
toward underrepresented mechanisms.

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
- `assets/` — vusa, ssln, sgln, iwrd, eqqq, brnt, crud, comm, comml, aigc, iind, imeu, wcoa, vuty
- `allocations/` — equal_weight, hrp_single, hrp_ward, trend_following, minimum_variance, risk_parity, momentum_top2, + others
- `overlays/` — vol_target_12/15/30pct, constraints_5_40/10_30, leverage_1x
- `composed/` — hrp_15/30vol, trend_15/30vol, hrp_with_constraints, trend_with_vol_12, trend_constrained_vol_target
- `portfolios/` — meta_trend_hrp_15/30vol, meta_multi_volatility, meta_ultimate, meta_all_season, + others

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
