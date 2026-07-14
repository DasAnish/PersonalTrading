"""
Low-MAX (lottery-avoidance) Defensive Tilt.

Long-only tilt away from "lottery-like" assets — those with high recent maximum
daily returns — toward assets with low MAX (Bali, Cakici & Whitelaw, 2011,
"Maxing Out: Stocks as Lotteries and the Cross-Section of Expected Returns",
Journal of Financial Economics 99(2)). Investors overpay for lottery-like payoffs,
so high-MAX assets subsequently underperform; holding the low-MAX cohort harvests
the mirror premium. Distinct from the volatility/beta tilts: MAX is an extreme
single-day tail feature, not average dispersion or systematic co-movement.

Reuses LowBetaTiltStrategy's ranking/selection machinery; the ranking key is the
trailing maximum daily return.
"""

from __future__ import annotations

import logging

import pandas as pd

from strategies.low_beta_defensive_tilt import LowBetaTiltStrategy

logger = logging.getLogger(__name__)


class LowMaxTiltStrategy(LowBetaTiltStrategy):
    """
    Low-MAX lottery-avoidance defensive tilt.

    Ranking key = each asset's average of its top-`n_max` daily returns over the
    lookback window (the MAX signal). Ranks ascending and equal-weights bottom_n
    (lowest-MAX). A market proxy is not required, but the parent's proxy plumbing
    is harmless.

    Parameters:
        beta_lookback_days: trailing window for the MAX signal (63, ~3 months).
        bottom_n: number of lowest-MAX assets to hold (5).
        n_max: number of top daily returns averaged into the MAX signal (5).
    """

    def __init__(self, underlying, beta_lookback_days: int = 63, bottom_n: int = 5, n_max: int = 5, name: str = None):
        super().__init__(
            underlying=underlying,
            beta_lookback_days=beta_lookback_days,
            bottom_n=bottom_n,
            name=name or f"Low-MAX Tilt (bottom_{bottom_n}, {beta_lookback_days}d)",
        )
        self.n_max = n_max

    def _compute_betas(self, prices: pd.DataFrame, market_proxy: str) -> pd.Series:
        # Ranking key is the MAX signal (avg of top-n daily returns), not beta.
        lookback_prices = prices.tail(self.beta_lookback_days + 1)
        returns = lookback_prices.pct_change().dropna()
        if len(returns) < self.n_max:
            return pd.Series(dtype=float)

        maxsig = {}
        for symbol in returns.columns:
            top = returns[symbol].nlargest(self.n_max)
            maxsig[symbol] = top.mean()
        return pd.Series(maxsig)
