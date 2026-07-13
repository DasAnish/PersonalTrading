"""
Network Risk Parity strategy using graph-theory asset weighting.

Based on "Network Risk Parity: graph theory-based portfolio construction"
(Journal of Asset Management, 2023).

Builds correlation network, computes centrality, and allocates risk inversely
to node centrality — peripheral assets get higher weight, densely-connected
clusters get downweighted.

Example:
    from strategies.core import AssetStrategy
    from strategies.network_risk_parity import NetworkRiskParityStrategy

    assets = [
        AssetStrategy('VUSA', currency='GBP'),
        AssetStrategy('SSLN', currency='GBP'),
        AssetStrategy('SGLN', currency='GBP'),
        AssetStrategy('IWRD', currency='GBP'),
    ]
    nrp = NetworkRiskParityStrategy(underlying=assets, lookback_days=252)
"""

import pandas as pd
import numpy as np
from typing import List, Literal
import logging

from scipy.sparse.csgraph import minimum_spanning_tree

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class NetworkRiskParityStrategy(AllocationStrategy):
    """
    Network Risk Parity portfolio allocation.

    Builds a minimum spanning tree from asset correlation matrix via scipy,
    computes node degree centrality, and allocates weight inversely to centrality.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 252,
        centrality_measure: Literal["degree", "eigenvector"] = "degree",
        graph_filter: Literal["mst", "threshold"] = "mst",
        threshold: float = 0.5,
        name: str = None,
    ):
        """
        Args:
            underlying: List of underlying strategies/assets
            lookback_days: Lookback for covariance estimate (default 252)
            centrality_measure: 'degree' (default, fast) or 'eigenvector'
            graph_filter: 'mst' (minimum spanning tree) or 'threshold'
            threshold: Correlation threshold if graph_filter='threshold'
            name: Display name
        """
        super().__init__(underlying, name=name or "Network Risk Parity")
        self.lookback_days = lookback_days
        self.centrality_measure = centrality_measure
        self.graph_filter = graph_filter
        self.threshold = threshold

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        if prices.empty or len(prices.columns) < 2:
            raise ValueError(
                f"Network Risk Parity requires at least 2 assets, got {len(prices.columns)}."
            )

        if len(prices) < 30:
            raise ValueError(
                f"Insufficient data. Need 30+ data points, got {len(prices)}."
            )

        prices = prices.ffill(limit=3).dropna()
        if len(prices) < 30:
            raise ValueError("Too many missing values after cleaning.")

        # Step 1: Compute correlation matrix
        lookback_prices = prices.iloc[-self.lookback_days:]
        returns = lookback_prices.pct_change().dropna()
        corr = returns.corr().values
        symbols = list(prices.columns)
        n = len(symbols)

        # Step 2: Build distance matrix (1 - |corr|) for MST
        if self.graph_filter == "mst":
            distances = 1.0 - np.abs(corr)
            # Set diagonal to 0 for MST algorithm
            np.fill_diagonal(distances, 0)

            # Compute MST using scipy
            mst = minimum_spanning_tree(distances, overwrite=False)

            # Convert MST to adjacency (dense for centrality computation)
            adj = mst.toarray()
            adj = adj + adj.T  # Make symmetric (MST gives lower triangular)

        else:  # threshold filter
            # Build adjacency from absolute correlation threshold
            adj = (np.abs(corr) > self.threshold).astype(float)
            np.fill_diagonal(adj, 0)

        # Step 3: Compute node centrality
        if self.centrality_measure == "degree":
            # Degree centrality = number of neighbors / (n - 1)
            degrees = np.sum(adj, axis=1)
            centrality = degrees / max(n - 1, 1)
        else:  # eigenvector (power iteration approximation)
            try:
                centrality = self._compute_eigenvector_centrality(adj)
            except Exception as e:
                logger.warning(
                    f"Eigenvector centrality failed: {e}. Falling back to degree."
                )
                degrees = np.sum(adj, axis=1)
                centrality = degrees / max(n - 1, 1)

        # Step 4: Weight inversely to centrality
        if np.sum(centrality) == 0:
            # Fallback to equal weight
            weights = np.ones(n) / n
        else:
            # Inverse centrality: high centrality -> low weight
            inv_centrality = 1.0 / (centrality + 1e-10)
            weights = inv_centrality / inv_centrality.sum()

        # Map to strategy names
        symbol_to_name = {}
        for strategy in self.underlying:
            for symbol in strategy.get_symbols():
                symbol_to_name[symbol] = strategy.name

        index = [symbol_to_name.get(s, s) for s in symbols]

        logger.debug(
            f"Network Risk Parity: degrees={dict(zip(symbols, np.sum(adj, axis=1)))}. "
            f"Weights: {dict(zip(symbols, weights[weights > 1e-6]))}"
        )

        return pd.Series(weights, index=index)

    @staticmethod
    def _compute_eigenvector_centrality(adj, max_iter=100, tol=1e-6):
        """
        Compute eigenvector centrality via power iteration.
        Returns normalized scores proportional to the leading eigenvector.
        """
        n = adj.shape[0]
        x = np.ones(n) / np.sqrt(n)

        for _ in range(max_iter):
            x_new = adj @ x
            x_norm = np.linalg.norm(x_new)
            if x_norm < 1e-10:
                break
            x_new = x_new / x_norm
            if np.linalg.norm(x_new - x) < tol:
                break
            x = x_new

        # Normalize to [0, 1]
        if x_norm > 0:
            return np.abs(x) / np.sum(np.abs(x))
        else:
            return np.ones(n) / n

    def get_strategy_lookback(self) -> int:
        return self.lookback_days
