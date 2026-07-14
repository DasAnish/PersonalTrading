"""
Betting-Against-Correlation (Low Average-Correlation) Defensive Tilt.

Long-only tilt toward assets with the lowest average pairwise correlation to the
rest of the universe (Asness, Frazzini, Gormsen & Pedersen, 2020, "Betting
Against Correlation: Testing Theories of the Low-Risk Effect", Journal of
Financial Economics 135(3)). The low-beta / low-risk premium decomposes into a
volatility component and a correlation component; BAC isolates the correlation
part, which the paper finds carries much of the low-risk effect and is more
consistent with leverage-constraint theories than with lottery-preference
theories. Holding the lowest-average-correlation assets harvests this premium
while maximising diversification.

Reuses LowBetaTiltStrategy's ranking/selection machinery; the ranking key is the
average pairwise correlation to the other assets.
"""

from __future__ import annotations

import logging

import pandas as pd
import numpy as np

from strategies.low_beta_defensive_tilt import LowBetaTiltStrategy

logger = logging.getLogger(__name__)


class LowCorrelationTiltStrategy(LowBetaTiltStrategy):
    """
    Betting-against-correlation defensive tilt.

    Ranking key = each asset's mean pairwise correlation to all other assets over
    the lookback window. Ranks ascending and equal-weights bottom_n (lowest
    average correlation). No market proxy required.

    Parameters:
        beta_lookback_days: trailing window for the correlation matrix (252).
        bottom_n: number of lowest-average-correlation assets to hold (5).
    """

    def __init__(self, underlying, beta_lookback_days: int = 252, bottom_n: int = 5, name: str = None):
        super().__init__(
            underlying=underlying,
            beta_lookback_days=beta_lookback_days,
            bottom_n=bottom_n,
            name=name or f"Betting-Against-Correlation Tilt (bottom_{bottom_n}, {beta_lookback_days}d)",
        )

    def _compute_betas(self, prices: pd.DataFrame, market_proxy: str) -> pd.Series:
        # Ranking key is average pairwise correlation, not beta.
        lookback_prices = prices.tail(self.beta_lookback_days + 1)
        returns = lookback_prices.pct_change().dropna()
        if len(returns) < 5 or returns.shape[1] < 2:
            return pd.Series(dtype=float)

        corr = returns.corr()
        # Mean correlation to others = (row sum - 1 (self)) / (N - 1).
        n = corr.shape[0]
        avg_corr = (corr.sum(axis=1) - 1.0) / (n - 1)
        return pd.Series(avg_corr)
