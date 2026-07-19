"""
Tail Risk Targeting overlay — target-CVaR exposure scaling.

Based on Rickenberg (2019), "Tail Risk Targeting: Target VaR and CVaR
Strategies" (SSRN 3444999): scaling exposure to a target CVaR instead of a
target volatility reacts specifically to left-tail thickening rather than
symmetric variance, giving better drawdown protection at similar or better
Sharpe. Works on the underlying's per-period portfolio-value returns; no
annualisation is applied — ``target_cvar`` is expressed per rebalance
period (e.g. 0.05 = 5% expected loss in the worst ``1 - alpha`` of months).
"""

import logging

import pandas as pd

from strategies.core import OverlayStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class TargetCVaRStrategy(OverlayStrategy):
    """
    Scale underlying weights so realised per-period CVaR hits the target.

    1. Take the underlying's portfolio values up to the current date and
       compute per-period returns over the trailing ``lookback_days`` window.
    2. Realised CVaR at ``alpha`` = mean of the worst ``(1 - alpha)`` share
       of returns, sign-flipped (a positive loss number).
    3. Scale = target_cvar / realised CVaR, capped to [0, 1] — scaling down
       parks the remainder in cash; never leverage.
    """

    def __init__(
        self,
        underlying: Strategy,
        target_cvar: float = 0.05,
        alpha: float = 0.95,
        lookback_days: int = 252,
    ):
        super().__init__(
            underlying, name=f"CVaR Target ({target_cvar*100:.0f}%, a={alpha:.2f})"
        )
        self.target_cvar = target_cvar
        self.alpha = alpha
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

        lookback_start = max(0, len(values_up_to_date) - self.lookback_days)
        returns = (
            values_up_to_date.iloc[lookback_start:].pct_change().dropna()
        )

        # Need enough observations for the tail to contain >= 1 point
        min_obs = max(10, int(round(1.0 / (1.0 - self.alpha))))
        if len(returns) < min_obs:
            return weights

        n_tail = max(1, int(len(returns) * (1.0 - self.alpha)))
        tail = returns.nsmallest(n_tail)
        realised_cvar = -tail.mean()

        if realised_cvar < 1e-8:
            # No realised losses in the window — stay fully invested
            return weights

        scale = self.target_cvar / realised_cvar
        scale = min(max(scale, 0.0), 1.0)

        return weights * scale
