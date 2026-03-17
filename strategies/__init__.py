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
    DataRequirements
)

# Concrete allocation strategies
from .hrp import HRPStrategy
from .equal_weight import EqualWeightStrategy
from .trend_following import TrendFollowingStrategy
from .minimum_variance import MinimumVarianceStrategy
from .risk_parity import RiskParityStrategy
from .momentum import MomentumTopNStrategy
from .volatility_momentum import VolatilityMomentumStrategy
from .trend_signal_mvo import TrendSignalMVOStrategy
from .mean_reversion import MeanReversionStrategy
from .skewness_weighted import SkewnessWeightedStrategy
from .meta_portfolio import MetaPortfolioStrategy
from .dual_momentum import DualMomentumStrategy
from .adaptive_asset_allocation import AdaptiveAssetAllocationStrategy
from .trend_signal_rp import TrendSignalRPStrategy
from .protective_asset_allocation import ProtectiveAssetAllocationStrategy

# Overlay strategies
from .overlays import (
    VolatilityTargetStrategy,
    ConstraintStrategy,
    LeverageStrategy
)

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

    assets_dir = Path(__file__).parent.parent / 'strategy_definitions' / 'assets'
    result = []
    for path in sorted(assets_dir.glob('*.json')):
        with open(path) as f:
            defn = json.load(f)
        params = defn.get('parameters', {})
        result.append(AssetStrategy(
            symbol=params.get('symbol', path.stem.upper()),
            currency=params.get('currency', 'GBP'),
            exchange=params.get('exchange', 'SMART'),
        ))
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
        super().__init__([
            AssetStrategy('AAPL', currency='USD'),
            AssetStrategy('MSFT', currency='USD'),
            AssetStrategy('GOOGL', currency='USD'),
            AssetStrategy('AMZN', currency='USD'),
        ])


__all__ = [
    # Core interfaces
    'Strategy',
    'AssetStrategy',
    'AllocationStrategy',
    'OverlayStrategy',
    'StrategyContext',
    'DataRequirements',
    # Allocation strategies
    'HRPStrategy',
    'EqualWeightStrategy',
    'TrendFollowingStrategy',
    'MinimumVarianceStrategy',
    'RiskParityStrategy',
    'MomentumTopNStrategy',
    'VolatilityMomentumStrategy',
    'TrendSignalMVOStrategy',
    'MeanReversionStrategy',
    'SkewnessWeightedStrategy',
    'MetaPortfolioStrategy',
    'DualMomentumStrategy',
    'AdaptiveAssetAllocationStrategy',
    'TrendSignalRPStrategy',
    'ProtectiveAssetAllocationStrategy',
    # Overlay strategies
    'VolatilityTargetStrategy',
    'ConstraintStrategy',
    'LeverageStrategy',
    # Market universe classes
    'UKETFsMarket',
    'USEquitiesMarket',
    # Legacy registry stubs
    'STRATEGY_REGISTRY',
    'create_strategy',
    'get_available_strategies',
]
