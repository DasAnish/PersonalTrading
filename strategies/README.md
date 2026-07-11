# strategies/

All strategy implementations and the composition primitives that combine them.

## Core primitives (`core.py`)
- `AssetStrategy` — a single tradable ETF leaf
- `AllocationStrategy` — base class; turns underlying assets/strategies into target weights
- `OverlayStrategy` — wraps another strategy to transform its weights

Strategies are **composable**: any strategy's `underlying` can be a list of assets *or* other strategies, so allocations and overlays nest arbitrarily.

## Allocation strategies
Classic portfolio construction: `hrp.py` (Hierarchical Risk Parity), `equal_weight.py`, `minimum_variance.py`, `risk_parity.py`, `maximum_diversification.py`, `adaptive_asset_allocation.py`, `protective_asset_allocation.py`.

Momentum / trend: `trend_following.py`, `momentum.py`, `dual_momentum.py`, `volatility_momentum.py`, `sma_trend_filter.py`, `carry_trend_filter.py`, `trend_signal_mvo.py`, `trend_signal_rp.py`.

Factor tilts: `low_volatility_tilt.py`, `low_beta_defensive_tilt.py`, `quality_weighted_stability.py`, `skewness_weighted.py`, `fifty_two_week_high.py`, `cross_asset_carry.py`.

Reversal / mean reversion: `mean_reversion.py`, `long_term_reversal.py`.

Seasonality: `halloween_seasonality.py`, `turn_of_month_seasonality.py`, `gold_autumn_seasonality.py`, `presidential_election_cycle.py`.

## Overlays
- `overlays.py` — `VolatilityTargetStrategy`, `VarianceTargetStrategy`, `ConstraintStrategy`, `LeverageStrategy`
- Risk overlays — `turbulence_overlay.py`, `gold_safe_haven_overlay.py`, `bond_duration_hedge_overlay.py`

## Support
- `catalog.py` — registry of available strategies
- `taxonomy.py` — mechanism/family classification used by overfitting analysis
- `strategy_loader.py` — builds strategy objects from `strategy_definitions/` YAML
- `meta_portfolio.py` — combines multiple strategies into one meta-portfolio

See [../docs/strategies.md](../docs/strategies.md) for algorithms and design rationale.
