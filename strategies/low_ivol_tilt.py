"""
Low Idiosyncratic-Volatility Defensive Tilt.

Long-only tilt toward assets with the lowest idiosyncratic volatility — the
standard deviation of the residual from a market-model regression (Ang, Hodrick,
Xing & Zhang, 2006, "The Cross-Section of Volatility and Expected Returns",
Journal of Finance 61(1)). Idiosyncratic volatility strips out market-driven
variance and isolates asset-specific risk; the low-IVOL cohort has historically
delivered superior risk-adjusted returns (the "IVOL puzzle"). Distinct from the
validated LowVolatilityTilt (total volatility) and LowBetaTilt (systematic beta):
this ranks on residual, market-neutralised volatility.

Reuses LowBetaTiltStrategy's ranking/selection machinery; the ranking key is
overridden from beta to idiosyncratic volatility.
"""

from __future__ import annotations

import logging

import pandas as pd

from strategies.low_beta_defensive_tilt import LowBetaTiltStrategy

logger = logging.getLogger(__name__)


class LowIVolTiltStrategy(LowBetaTiltStrategy):
    """
    Low idiosyncratic-volatility defensive tilt.

    Identical to LowBetaTiltStrategy except the ranking key is each asset's
    idiosyncratic volatility: fit r_asset = a + b * r_mkt over the lookback,
    take the standard deviation of the residuals. Ranks ascending and
    equal-weights bottom_n (lowest-IVOL).

    Parameters:
        beta_lookback_days: trailing window for the market-model fit (252).
        bottom_n: number of lowest-IVOL assets to hold (5).
    """

    def __init__(self, underlying, beta_lookback_days: int = 252, bottom_n: int = 5, name: str = None):
        super().__init__(
            underlying=underlying,
            beta_lookback_days=beta_lookback_days,
            bottom_n=bottom_n,
            name=name or f"Low IVol Tilt (bottom_{bottom_n}, {beta_lookback_days}d)",
        )

    def _compute_betas(self, prices: pd.DataFrame, market_proxy: str) -> pd.Series:
        # Ranking key is idiosyncratic vol (residual std), not beta.
        lookback_prices = prices.tail(self.beta_lookback_days + 1)
        returns = lookback_prices.pct_change().dropna()

        if len(returns) < 5 or market_proxy not in returns.columns:
            return pd.Series(dtype=float)

        market = returns[market_proxy]
        market_var = market.var()
        if market_var <= 0:
            return pd.Series(dtype=float)
        market_mean = market.mean()

        ivol = {}
        for symbol in returns.columns:
            if symbol == market_proxy:
                ivol[symbol] = 0.0  # market has zero idiosyncratic vol by definition
                continue
            asset = returns[symbol]
            beta = asset.cov(market) / market_var
            alpha = asset.mean() - beta * market_mean
            resid = asset - (alpha + beta * market)
            ivol[symbol] = resid.std()
        return pd.Series(ivol)
