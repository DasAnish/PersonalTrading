"""
Low-Beta Defensive Tilt strategy.

Long-only implementation of Betting-Against-Beta (BAB) factor. Tilts portfolio
toward low-beta assets (assets with low systematic co-movement with the market)
and away from high-beta assets, capturing the defensive risk-reduction benefit
of the BAB premium.

Based on Frazzini & Pedersen (2014) "Betting Against Beta" which documents that
low-beta assets earn higher risk-adjusted returns than high-beta assets due to
leverage/funding constraints. This long-only version emphasizes defensive
characteristics: lower drawdown and volatility with similar or modestly lower
total return than cap-weight, improving risk-adjusted metrics.

References:
- Frazzini & Pedersen (2014): "Betting Against Beta", Journal of Financial Economics 111(1) 1-25
- Long-only tilt toward low-beta, defensive assets
- Market proxy: IWRD (world equities) or VUSA (US equities)

Example:
    assets = [AssetStrategy('VUSA'), ..., AssetStrategy('SGLN')]
    strategy = LowBetaTiltStrategy(
        underlying=assets,
        beta_lookback_days=126,
        bottom_n=5
    )
    weights = strategy.calculate_weights(context)
"""

from __future__ import annotations

import logging
from typing import List, Optional

import pandas as pd
import numpy as np

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)

# Market proxies for beta estimation
MARKET_PROXY_PRIMARY = 'IWRD'  # World equities (primary)
MARKET_PROXY_FALLBACK = 'VUSA'  # US equities (fallback)


class LowBetaTiltStrategy(AllocationStrategy):
    """
    Low-Beta Defensive Tilt allocation strategy.

    Estimates each asset's beta to the world equity portfolio (IWRD or VUSA)
    over a trailing window, ranks by beta ascending, and equal-weights the
    lowest-beta assets. This long-only tilt captures the defensive benefits
    of the BAB (Betting Against Beta) factor: lower volatility and drawdown
    with similar or modestly lower returns, improving risk-adjusted metrics.

    Only uses assets present in the rebalance universe. Falls back gracefully
    when sufficient price data is unavailable.

    Attributes:
        beta_lookback_days: Trailing window for beta estimation (default 126)
        bottom_n: Number of lowest-beta assets to hold (default 5)
        market_proxy: Symbol of market proxy (IWRD or VUSA)
    """

    def __init__(
        self,
        underlying: List[Strategy],
        beta_lookback_days: int = 126,
        bottom_n: int = 5,
        name: str = None,
    ):
        """
        Initialize Low-Beta Tilt strategy.

        Args:
            underlying: List of underlying strategies (assets)
            beta_lookback_days: Trailing days for beta estimation (default 126 = 6m)
            bottom_n: Number of lowest-beta assets to hold (default 5)
            name: Display name
        """
        super().__init__(
            underlying=underlying,
            name=name or f"Low-Beta Tilt (bottom_{bottom_n}, {beta_lookback_days}d)",
        )
        self.beta_lookback_days = beta_lookback_days
        self.bottom_n = min(max(bottom_n, 1), len(underlying))

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        """
        Calculate low-beta tilt weights: equal-weight bottom_n by beta.

        Args:
            context: StrategyContext with prices and current_date

        Returns:
            pd.Series with index=asset names, values=weights.
            Weights sum to 1.0 (long-only).

        Logic:
            1. Identify market proxy (IWRD or VUSA)
            2. Compute daily returns for all assets and market proxy
            3. Estimate beta = cov(asset_returns, market_returns) / var(market)
            4. Rank by beta (ascending)
            5. Equal-weight bottom_n, zero the rest
            6. Normalize to sum 1.0
        """
        prices = context.prices
        available_symbols = set(prices.columns)

        # Build symbol -> strategy name mapping
        symbol_to_name = self._build_name_map()
        strategy_names = [s.name for s in self.underlying]

        # Initialize weights (all zeros)
        weights = pd.Series(0.0, index=strategy_names)

        # Check if we have sufficient data
        if len(prices) < self.beta_lookback_days + 1:
            logger.debug(
                f"LowBetaTilt: insufficient price history ({len(prices)} < {self.beta_lookback_days + 1}), "
                f"falling back to equal weight"
            )
            return pd.Series(1.0 / len(strategy_names), index=strategy_names)

        # Find market proxy
        market_proxy = None
        if MARKET_PROXY_PRIMARY in available_symbols:
            market_proxy = MARKET_PROXY_PRIMARY
        elif MARKET_PROXY_FALLBACK in available_symbols:
            market_proxy = MARKET_PROXY_FALLBACK
            logger.debug(
                f"LowBetaTilt: {MARKET_PROXY_PRIMARY} not available, "
                f"using {MARKET_PROXY_FALLBACK} as market proxy"
            )

        if not market_proxy:
            logger.debug(
                "LowBetaTilt: no market proxy available, falling back to equal weight"
            )
            return pd.Series(1.0 / len(strategy_names), index=strategy_names)

        # Compute betas for each asset
        betas = self._compute_betas(prices, market_proxy)

        logger.debug(f"LowBetaTilt betas: {dict(betas.round(4))}")

        # Filter to available assets with valid betas
        valid_betas = betas[betas.index.isin(available_symbols)]

        if len(valid_betas) == 0:
            logger.debug("LowBetaTilt: no valid betas, falling back to equal weight")
            return pd.Series(1.0 / len(strategy_names), index=strategy_names)

        # Rank by beta (ascending) and select bottom_n
        ranked = valid_betas.sort_values()
        bottom_symbols = ranked.index[: self.bottom_n].tolist()

        logger.debug(
            f"LowBetaTilt: ranked by beta (ascending) = {dict(ranked.round(4))}. "
            f"Bottom {self.bottom_n}: {bottom_symbols}"
        )

        # Assign equal weight to bottom_n, zero to rest
        num_bottom = len(bottom_symbols)
        if num_bottom > 0:
            equal_weight = 1.0 / num_bottom
            for symbol in bottom_symbols:
                strategy_name = symbol_to_name.get(symbol, symbol)
                weights[strategy_name] = equal_weight

        logger.debug(f"LowBetaTilt weights: {dict(weights[weights > 0].round(4))}")

        return weights

    def get_strategy_lookback(self) -> int:
        """
        Low-Beta Tilt requires trailing data for beta estimation.

        Returns:
            beta_lookback_days (default 126)
        """
        return self.beta_lookback_days

    def _compute_betas(self, prices: pd.DataFrame, market_proxy: str) -> pd.Series:
        """
        Compute beta for each asset relative to market proxy.

        Beta = covariance(asset_returns, market_returns) / variance(market_returns)

        Args:
            prices: Price DataFrame with all symbols
            market_proxy: Symbol of market proxy (e.g., 'IWRD')

        Returns:
            pd.Series with index=symbols, values=beta estimates.
            Returns empty if insufficient data.
        """
        # Slice to lookback window and compute returns
        lookback_prices = prices.tail(self.beta_lookback_days + 1)
        returns = lookback_prices.pct_change().dropna()

        if len(returns) < 2:
            return pd.Series(dtype=float)

        if market_proxy not in returns.columns:
            return pd.Series(dtype=float)

        market_returns = returns[market_proxy]
        market_var = market_returns.var()

        if market_var <= 0:
            logger.warning(f"LowBetaTilt: market proxy {market_proxy} has zero variance")
            return pd.Series(dtype=float)

        # Compute beta for each asset
        betas = {}
        for symbol in returns.columns:
            if symbol == market_proxy:
                betas[symbol] = 1.0  # Market has beta=1 by definition
            else:
                asset_returns = returns[symbol]
                covariance = asset_returns.cov(market_returns)
                beta = covariance / market_var
                betas[symbol] = beta

        return pd.Series(betas)

    def _build_name_map(self) -> dict:
        """Build mapping from symbol to strategy name."""
        symbol_to_name = {}
        for strategy in self.underlying:
            for symbol in strategy.get_symbols():
                symbol_to_name[symbol] = strategy.name
        return symbol_to_name
