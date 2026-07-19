"""
CPPI Drawdown-Floor overlay (constant proportion portfolio insurance).

Based on Black & Perold (1992), "Theory of constant proportion portfolio
insurance", Journal of Economic Dynamics and Control 16(3-4). Exposure =
multiplier x cushion, cushion = (NAV - floor)/NAV, with the floor ratcheted
to ``floor_fraction`` of the running NAV peak so realised drawdown is
mechanically capped near ``1 - floor_fraction`` (soft cap at monthly
cadence). A convexity transform, not an alpha source: judged on drawdown
reduction per unit of Sharpe given up.
"""

import logging

import pandas as pd

from strategies.core import OverlayStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class CPPIStrategy(OverlayStrategy):
    """Scale underlying weights by min(1, multiplier x cushion)."""

    def __init__(
        self,
        underlying: Strategy,
        floor_fraction: float = 0.85,
        multiplier: float = 3.0,
        lookback_days: int = 252,
    ):
        super().__init__(
            underlying,
            name=f"CPPI (floor {floor_fraction*100:.0f}%, m={multiplier:g})",
        )
        if not 0.0 < floor_fraction < 1.0:
            raise ValueError(f"floor_fraction must be in (0,1), got {floor_fraction}")
        if multiplier <= 0:
            raise ValueError(f"multiplier must be positive, got {multiplier}")
        self.floor_fraction = floor_fraction
        self.multiplier = multiplier
        self.lookback_days = lookback_days

    def get_overlay_lookback(self) -> int:
        return self.lookback_days

    def transform_weights(
        self, weights: pd.Series, context: StrategyContext
    ) -> pd.Series:
        portfolio_values = context.portfolio_values

        if portfolio_values is None or len(portfolio_values) < 2:
            return weights

        values_up_to_date = portfolio_values[
            portfolio_values.index <= context.current_date
        ]
        if len(values_up_to_date) < 2:
            return weights

        nav = float(values_up_to_date.iloc[-1])
        peak = float(values_up_to_date.max())
        floor = self.floor_fraction * peak

        cushion = max(0.0, nav - floor) / nav if nav > 0 else 0.0
        exposure = min(1.0, self.multiplier * cushion)

        return weights * exposure
