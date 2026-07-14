"""
Portfolio optimization strategies using new unified architecture.

All strategies inherit from the unified Strategy interface in core.py:
- AssetStrategy: Individual instruments (VUSA, AAPL, etc.)
- AllocationStrategy: Portfolio allocation (HRP, TrendFollowing, EqualWeight)
- OverlayStrategy: Weight transformations (VolTarget, Constraints, etc.)

Strategies are composable and can be nested at any depth.

Example:
    from strategies.core import AssetStrategy
    from strategies.hrp import HRPStrategy
    from strategies.overlays import VolatilityTargetStrategy

    # Assets as strategies
    assets = [
        AssetStrategy('VUSA', currency='GBP'),
        AssetStrategy('SSLN', currency='GBP'),
    ]

    # Portfolio strategy
    hrp = HRPStrategy(underlying=assets, linkage_method='ward')

    # Overlay on portfolio
    vol_target = VolatilityTargetStrategy(underlying=hrp, target_vol=0.12)

    # Meta-portfolio (portfolio of strategies)
    from strategies.equal_weight import EqualWeightStrategy
    meta = EqualWeightStrategy(underlying=[hrp, vol_target])
"""

# Core interfaces
from .core import (
    Strategy,
    AssetStrategy,
    AllocationStrategy,
    OverlayStrategy,
    StrategyContext,
    DataRequirements,
    prune_missing_assets,
)

# Concrete allocation strategies
from .hrp import HRPStrategy
from .herc import HERCStrategy
from .equal_weight import EqualWeightStrategy
from .trend_following import TrendFollowingStrategy
from .minimum_variance import MinimumVarianceStrategy
from .minimum_semivariance import MinimumSemivarianceStrategy
from .minimum_cvar import MinimumCVaRStrategy
from .maximum_diversification import MaximumDiversificationStrategy
from .risk_parity import RiskParityStrategy
from .momentum import MomentumTopNStrategy
from .fifty_two_week_high import FiftyTwoWeekHighStrategy
from .volatility_timing import VolatilityTimingStrategy
from .volatility_momentum import VolatilityMomentumStrategy
from .trend_signal_mvo import TrendSignalMVOStrategy
from .mean_reversion import MeanReversionStrategy
from .long_term_reversal import LongTermReversalStrategy
from .short_term_reversal import ShortTermReversalStrategy
from .skewness_weighted import SkewnessWeightedStrategy
from .meta_portfolio import MetaPortfolioStrategy
from .dual_momentum import DualMomentumStrategy
from .residual_momentum import ResidualMomentumStrategy
from .accelerating_dual_momentum import AcceleratingDualMomentumStrategy
from .adaptive_asset_allocation import AdaptiveAssetAllocationStrategy
from .flexible_asset_allocation import FlexibleAssetAllocationStrategy
from .trend_signal_rp import TrendSignalRPStrategy
from .protective_asset_allocation import ProtectiveAssetAllocationStrategy
from .commodity_momentum_correlation_filter import (
    CommodityMomentumCorrelationStrategy,
)
from .halloween_seasonality import HalloweenSeasonalityStrategy
from .turn_of_month_seasonality import TurnOfMonthSeasonalityStrategy
from .cross_asset_carry import CarryTiltStrategy
from .gold_safe_haven_overlay import GoldSafeHavenOverlayStrategy
from .bond_duration_hedge_overlay import BondDurationHedgeOverlayStrategy
from .treasury_flight_to_quality_overlay import TreasuryFlightToQualityOverlayStrategy
from .dynamic_crisis_hedge_overlay import DynamicCrisisHedgeOverlayStrategy
from .low_beta_defensive_tilt import LowBetaTiltStrategy
from .quality_weighted_stability import QualityWeightedStabilityStrategy
from .presidential_election_cycle import PresidentialCycleSeasonalityStrategy
from .carry_trend_filter import CarryTrendFilterStrategy
from .gold_autumn_seasonality import GoldAutumnSeasonalityStrategy
from .sma_trend_filter import SMATrendFilterStrategy
from .low_volatility_tilt import LowVolatilityTiltStrategy
from .time_series_momentum import TimeSeriesMomentumStrategy
from .network_risk_parity import NetworkRiskParityStrategy
from .seasonal_return_tilt import SeasonalReturnTiltStrategy
from .defensive_asset_allocation import DefensiveAssetAllocationStrategy
from .vigilant_asset_allocation import VigilantAssetAllocationStrategy
from .gold_silver_ratio import GoldSilverRatioStrategy
from .national_market_mean_reversion import NationalMarketMeanReversionStrategy
from .stock_bond_correlation_regime import StockBondCorrelationRegimeStrategy
from .strategy_risk_parity_meta import StrategyRiskParityMetaStrategy

# Overlay strategies
from .overlays import VolatilityTargetStrategy, ConstraintStrategy, LeverageStrategy
from .turbulence_overlay import TurbulenceOverlayStrategy

# ---------------------------------------------------------------------------
# Legacy registry stubs — kept for backward compatibility with run_backtest.py
# (non-YAML code paths).  STRATEGY_REGISTRY is intentionally empty because the
# project now uses YAML definitions exclusively.
# ---------------------------------------------------------------------------

STRATEGY_REGISTRY: dict = {}


def create_strategy(strategy_key: str, **kwargs):
    """Build a strategy from the legacy registry (not used in YAML/--all mode)."""
    raise NotImplementedError(
        f"create_strategy('{strategy_key}') is not supported; "
        "use StrategyLoader.build_strategy() with YAML definitions instead."
    )


def get_available_strategies() -> list:
    """Return available strategy keys (legacy registry — always empty)."""
    return list(STRATEGY_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Market universe convenience classes (used by YAML strategy definitions)
# ---------------------------------------------------------------------------


def _load_uk_etf_assets() -> list:
    """Dynamically load all UK ETFs from strategy_definitions/assets/*.json."""
    import json
    from pathlib import Path

    assets_dir = Path(__file__).parent.parent / "strategy_definitions" / "assets"
    result = []
    for path in sorted(assets_dir.glob("*.json")):
        with open(path) as f:
            defn = json.load(f)
        params = defn.get("parameters", {})
        result.append(
            AssetStrategy(
                symbol=params.get("symbol", path.stem.upper()),
                currency=params.get("currency", "GBP"),
                exchange=params.get("exchange", "SMART"),
            )
        )
    return result


class UKETFsMarket(list):
    """UK ETF universe: all assets defined in strategy_definitions/assets/ (GBP).

    Behaves exactly like List[AssetStrategy] so it can be passed as the
    `underlying` parameter of any AllocationStrategy.
    """

    def __init__(self):
        super().__init__(_load_uk_etf_assets())


class USEquitiesMarket(list):
    """US large-cap tech universe: AAPL, MSFT, GOOGL, AMZN (USD).

    Behaves exactly like List[AssetStrategy] so it can be passed as the
    `underlying` parameter of any AllocationStrategy.
    """

    def __init__(self):
        super().__init__(
            [
                AssetStrategy("AAPL", currency="USD"),
                AssetStrategy("MSFT", currency="USD"),
                AssetStrategy("GOOGL", currency="USD"),
                AssetStrategy("AMZN", currency="USD"),
            ]
        )


__all__ = [
    # Core interfaces
    "Strategy",
    "AssetStrategy",
    "AllocationStrategy",
    "OverlayStrategy",
    "StrategyContext",
    "DataRequirements",
    "prune_missing_assets",
    # Allocation strategies
    "HRPStrategy",
    "HERCStrategy",
    "EqualWeightStrategy",
    "TrendFollowingStrategy",
    "MinimumVarianceStrategy",
    "MinimumSemivarianceStrategy",
    "MinimumCVaRStrategy",
    "MaximumDiversificationStrategy",
    "RiskParityStrategy",
    "MomentumTopNStrategy",
    "FiftyTwoWeekHighStrategy",
    "VolatilityTimingStrategy",
    "VolatilityMomentumStrategy",
    "TrendSignalMVOStrategy",
    "MeanReversionStrategy",
    "LongTermReversalStrategy",
    "ShortTermReversalStrategy",
    "SkewnessWeightedStrategy",
    "MetaPortfolioStrategy",
    "DualMomentumStrategy",
    "ResidualMomentumStrategy",
    "AcceleratingDualMomentumStrategy",
    "AdaptiveAssetAllocationStrategy",
    "FlexibleAssetAllocationStrategy",
    "TrendSignalRPStrategy",
    "ProtectiveAssetAllocationStrategy",
    "CommodityMomentumCorrelationStrategy",
    "HalloweenSeasonalityStrategy",
    "TurnOfMonthSeasonalityStrategy",
    "CarryTiltStrategy",
    "GoldSafeHavenOverlayStrategy",
    "BondDurationHedgeOverlayStrategy",
    "TreasuryFlightToQualityOverlayStrategy",
    "DynamicCrisisHedgeOverlayStrategy",
    "LowBetaTiltStrategy",
    "QualityWeightedStabilityStrategy",
    "PresidentialCycleSeasonalityStrategy",
    "CarryTrendFilterStrategy",
    "GoldAutumnSeasonalityStrategy",
    "SMATrendFilterStrategy",
    "LowVolatilityTiltStrategy",
    "TimeSeriesMomentumStrategy",
    "NetworkRiskParityStrategy",
    "SeasonalReturnTiltStrategy",
    "DefensiveAssetAllocationStrategy",
    "VigilantAssetAllocationStrategy",
    "GoldSilverRatioStrategy",
    "NationalMarketMeanReversionStrategy",
    "StockBondCorrelationRegimeStrategy",
    "StrategyRiskParityMetaStrategy",
    # Overlay strategies
    "VolatilityTargetStrategy",
    "ConstraintStrategy",
    "LeverageStrategy",
    "TurbulenceOverlayStrategy",
    # Market universe classes
    "UKETFsMarket",
    "USEquitiesMarket",
    # Legacy registry stubs
    "STRATEGY_REGISTRY",
    "create_strategy",
    "get_available_strategies",
]
