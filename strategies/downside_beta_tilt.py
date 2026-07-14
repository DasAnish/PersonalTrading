"""
Low Downside-Beta Defensive Tilt strategy.

Long-only defensive tilt toward assets with low *downside* beta — systematic
co-movement with the market estimated only on days the market falls (Ang, Chen &
Xing, 2006, "Downside Risk", Review of Financial Studies 19(4)). Downside beta
isolates crash co-movement, which the paper shows is priced separately from
ordinary market beta. The long-only version holds the lowest-downside-beta
assets: the ones that decouple from the market precisely when it sells off,
giving a defensive, shallow-drawdown profile distinct from the validated
full-beta (LowBetaTilt) and total-volatility (LowVolatilityTilt) tilts.

Reuses LowBetaTiltStrategy's ranking/selection machinery; only the beta
estimator is overridden to condition on down-market observations.
"""

from __future__ import annotations

import logging

import pandas as pd

from strategies.low_beta_defensive_tilt import LowBetaTiltStrategy

logger = logging.getLogger(__name__)


class DownsideBetaTiltStrategy(LowBetaTiltStrategy):
    """
    Low downside-beta defensive tilt.

    Identical to LowBetaTiltStrategy except beta is estimated only over the
    subset of the lookback window where the market proxy return is below its
    mean (down-market days): downside_beta = cov(r_asset, r_mkt | r_mkt<mean_mkt)
    / var(r_mkt | r_mkt<mean_mkt). Ranks ascending and equal-weights bottom_n.

    Parameters:
        beta_lookback_days: trailing window for downside-beta estimation (252).
        bottom_n: number of lowest-downside-beta assets to hold (5).
    """

    def __init__(self, underlying, beta_lookback_days: int = 252, bottom_n: int = 5, name: str = None):
        super().__init__(
            underlying=underlying,
            beta_lookback_days=beta_lookback_days,
            bottom_n=bottom_n,
            name=name or f"Low Downside-Beta Tilt (bottom_{bottom_n}, {beta_lookback_days}d)",
        )

    def _compute_betas(self, prices: pd.DataFrame, market_proxy: str) -> pd.Series:
        lookback_prices = prices.tail(self.beta_lookback_days + 1)
        returns = lookback_prices.pct_change().dropna()

        if len(returns) < 2 or market_proxy not in returns.columns:
            return pd.Series(dtype=float)

        market_returns = returns[market_proxy]
        # Condition on down-market days: market return below its trailing mean.
        down_mask = market_returns < market_returns.mean()
        down_returns = returns[down_mask]
        down_market = down_returns[market_proxy]

        if len(down_returns) < 5 or down_market.var() <= 0:
            # Not enough down days to estimate a stable downside beta.
            return pd.Series(dtype=float)

        market_var = down_market.var()
        betas = {}
        for symbol in down_returns.columns:
            if symbol == market_proxy:
                betas[symbol] = 1.0
            else:
                cov = down_returns[symbol].cov(down_market)
                betas[symbol] = cov / market_var
        return pd.Series(betas)
