"""
Hierarchical Risk Parity (HRP) portfolio optimization strategy.

Implementation based on:
- De Prado, M. L. (2016). "Building Diversified Portfolios that Outperform Out of Sample"
- Reference notebook: references/Hierarchical-Risk-Parity/Hierarchical Clustering.ipynb

The HRP algorithm consists of three stages:
1. Tree Clustering: Use hierarchical clustering on correlation matrix
2. Quasi-Diagonalization: Reorganize covariance matrix by cluster similarity
3. Recursive Bisection: Allocate weights inversely proportional to cluster variance

Example:
    from strategies.core import AssetStrategy
    from strategies.hrp import HRPStrategy
    from backtesting.engine import BacktestEngine

    # Create asset strategies
    assets = [
        AssetStrategy('VUSA', currency='GBP'),
        AssetStrategy('SSLN', currency='GBP'),
        AssetStrategy('SGLN', currency='GBP'),
        AssetStrategy('IWRD', currency='GBP'),
    ]

    # Create HRP strategy
    hrp = HRPStrategy(underlying=assets, linkage_method='ward')

    # Run backtest
    engine = BacktestEngine(initial_capital=10000)
    results = await engine.run_backtest(hrp, start_date, end_date)
"""

import pandas as pd
import numpy as np
from scipy.cluster.hierarchy import linkage
from typing import List

from strategies.core import AllocationStrategy, Strategy, StrategyContext


def get_quasi_diag(link: np.ndarray) -> List[int]:
    """
    Reorganize items into quasi-diagonal order based on hierarchical clustering.

    This function traverses the linkage matrix from root to leaves, recursively
    expanding clusters into their constituent items while preserving the
    hierarchical ordering.

    Args:
        link: Linkage matrix from scipy.cluster.hierarchy.linkage()
              Shape (N-1, 4) where N is number of items
              Each row: [cluster1_id, cluster2_id, distance, num_items]

    Returns:
        List of asset indices in quasi-diagonal order
        Similar assets are placed together in the list

    Example:
        >>> link = np.array([[0, 1, 0.5, 2], [2, 3, 0.7, 2]])
        >>> get_quasi_diag(link)
        [0, 1, 2, 3]  # or similar ordering based on clustering
    """
    link = link.astype(int)

    # Start with the last tuple (root of tree)
    # Contains the final merge of two largest clusters
    sort_ix = pd.Series([link[-1, 0], link[-1, 1]])

    # Total number of original items
    num_items = link[-1, 3]

    # Iteratively expand cluster IDs into individual item IDs
    while sort_ix.max() >= num_items:
        # Create odd-numbered indices to leave space for insertions
        sort_ix.index = range(0, sort_ix.shape[0] * 2, 2)

        # Find entries that are still cluster IDs (not individual items)
        df0 = sort_ix[sort_ix >= num_items]

        # Get positions and cluster indices
        i = df0.index  # Positions of clusters in sort_ix
        j = df0.values - num_items  # Convert cluster IDs to linkage matrix row indices

        # Replace cluster ID with first constituent
        sort_ix[i] = link[j, 0]

        # Insert second constituent at odd indices
        df0 = pd.Series(link[j, 1], index=i + 1)
        sort_ix = pd.concat([sort_ix, df0])

        # Resort and reset index
        sort_ix = sort_ix.sort_index()
        sort_ix.index = range(sort_ix.shape[0])

    return sort_ix.tolist()


def get_cluster_var(cov: pd.DataFrame, c_items: List[int]) -> float:
    """
    Calculate variance of a cluster using inverse-variance portfolio.

    This function computes the variance of an inverse-variance weighted
    portfolio formed from the assets in the cluster. The inverse-variance
    portfolio gives more weight to less volatile assets.

    Args:
        cov: Covariance matrix (DataFrame with index and columns as asset indices)
        c_items: List of asset indices in the cluster

    Returns:
        Portfolio variance for the cluster

    Example:
        >>> cov = pd.DataFrame([[0.04, 0.01], [0.01, 0.09]])
        >>> get_cluster_var(cov, [0, 1])
        0.0285  # approximate value
    """
    # Extract sub-covariance matrix for items in cluster
    cov_ = cov.iloc[c_items, c_items]

    # Inverse-variance portfolio: weight proportional to 1/variance
    ivp = 1.0 / np.diag(cov_)  # Inverse of diagonal (variances)
    ivp /= ivp.sum()  # Normalize to sum to 1

    # Calculate portfolio variance: w' * Cov * w
    w_ = ivp.reshape(-1, 1)  # Column vector
    c_var = np.dot(np.dot(w_.T, cov_), w_)[0, 0]

    return c_var


def get_rec_bipart(cov: pd.DataFrame, sort_ix: List[int]) -> pd.Series:
    """
    Compute HRP weights using recursive bisection.

    This function implements the core HRP weight allocation algorithm:
    1. Start with all weights equal to 1
    2. Recursively split the sorted list of assets into two halves
    3. For each split, allocate weight inversely proportional to cluster variance
    4. Continue until individual assets remain

    Args:
        cov: Covariance matrix (DataFrame)
        sort_ix: List of asset indices in quasi-diagonal order (from get_quasi_diag)

    Returns:
        Series with index=asset_indices, values=portfolio weights
        Weights sum to 1.0

    Example:
        >>> cov = pd.DataFrame(...)
        >>> sort_ix = [2, 4, 3, 5, 0, 1]
        >>> weights = get_rec_bipart(cov, sort_ix)
        >>> weights.sum()
        1.0
    """
    # Initialize all weights to 1
    w = pd.Series(1.0, index=sort_ix)

    # Start with all items in one cluster
    c_items = [sort_ix]

    # Recursively bisect until all items are separated
    while len(c_items) > 0:
        # Bisect each cluster into two halves
        # [(0, mid), (mid, end)] for each cluster
        c_items = [
            i[int(j):int(k)]
            for i in c_items
            for j, k in ((0, len(i) / 2), (len(i) / 2, len(i)))
            if len(i) > 1  # Only split clusters with more than 1 item
        ]

        # Allocate weights between adjacent cluster pairs
        for i in range(0, len(c_items), 2):
            c_items0 = c_items[i]  # Left cluster
            c_items1 = c_items[i + 1]  # Right cluster

            # Calculate variance for each cluster
            c_var0 = get_cluster_var(cov, c_items0)
            c_var1 = get_cluster_var(cov, c_items1)

            # Allocate weight inversely proportional to variance
            # Lower variance → higher weight
            alpha = 1 - c_var0 / (c_var0 + c_var1)

            # Update weights: multiply by allocation factor
            w[c_items0] *= alpha  # Left cluster gets alpha
            w[c_items1] *= (1 - alpha)  # Right cluster gets (1 - alpha)

    return w


class HRPStrategy(AllocationStrategy):
    """
    Hierarchical Risk Parity (HRP) portfolio optimization strategy.

    HRP is a modern portfolio optimization technique that:
    - Uses machine learning (hierarchical clustering) to identify asset relationships
    - Allocates weights based on inverse-variance principles within cluster hierarchy
    - More stable than mean-variance optimization with correlated assets
    - Does not require matrix inversion (unlike Markowitz)

    The algorithm has three stages:
    1. Tree Clustering: Build hierarchical cluster tree from correlation matrix
    2. Quasi-Diagonalization: Reorganize assets by cluster similarity
    3. Recursive Bisection: Allocate weights inversely to cluster variance

    Example:
        assets = [
            AssetStrategy('VUSA', currency='GBP'),
            AssetStrategy('SSLN', currency='GBP'),
            AssetStrategy('SGLN', currency='GBP'),
            AssetStrategy('IWRD', currency='GBP'),
        ]
        hrp = HRPStrategy(underlying=assets, linkage_method='ward')
    """

    def __init__(
        self,
        underlying: List[Strategy],
        linkage_method: str = "single",
        name: str = None
    ):
        """
        Initialize HRP strategy.

        Args:
            underlying: List of underlying strategies (assets or portfolios)
            linkage_method: Linkage criterion for hierarchical clustering
                          'single' = nearest neighbor (default, as in reference)
                          'complete' = furthest neighbor
                          'average' = average distance
                          'ward' = minimize variance
            name: Display name (default: "HRP")
        """
        super().__init__(underlying, name=name or "Hierarchical Risk Parity")
        self.linkage_method = linkage_method

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        """
        Calculate HRP portfolio weights from historical prices.

        Args:
            context: StrategyContext with prices and metadata
                    Prices must have sufficient history for correlation calculation
                    (recommended: at least 252 trading days)

        Returns:
            pd.Series with index=strategy names, values=weights (sum to 1.0)

        Raises:
            ValueError: If insufficient data or invalid input
                       Requires at least 2 assets and 30 data points
        """
        # Extract prices from context
        prices = context.prices

        # Validation
        if prices.empty or len(prices.columns) < 2:
            raise ValueError(
                "HRP requires at least 2 assets. "
                f"Received {len(prices.columns)} assets."
            )

        if len(prices) < 30:
            raise ValueError(
                f"Insufficient data for HRP. "
                f"Requires at least 30 data points, received {len(prices)}."
            )

        # Handle NaN values
        if prices.isnull().any().any():
            # Forward fill missing values (max 3 days)
            prices = prices.ffill(limit=3)
            # Drop any remaining NaN
            prices = prices.dropna()

            if len(prices) < 30:
                raise ValueError(
                    "Too many missing values. Insufficient data after cleaning."
                )

        # ===== Stage 1: Tree Clustering =====

        # Calculate returns
        returns = prices.pct_change().dropna()

        # Calculate correlation matrix
        corr = returns.corr()

        # Convert correlation to distance matrix
        # Formula: d = sqrt(0.5 * (1 - corr))
        # Maps correlation [-1, 1] to distance [0, 1]
        d_corr = np.sqrt(0.5 * (1 - corr))

        # Perform hierarchical clustering
        # Returns linkage matrix: (N-1) x 4 array
        link = linkage(d_corr.values, method=self.linkage_method)

        # ===== Stage 2: Quasi-Diagonalization =====

        # Get quasi-diagonal ordering of assets
        sort_ix = get_quasi_diag(link)

        # ===== Stage 3: Recursive Bisection =====

        # Calculate covariance matrix
        cov = returns.cov()

        # Calculate HRP weights using recursive bisection
        weights = get_rec_bipart(cov, sort_ix)

        # Map from integer indices back to symbol/strategy names
        # First get the symbols from prices, then map to strategy names
        symbols = list(prices.columns)
        symbol_to_strategy_name = {}

        # Build mapping from symbol to strategy name
        for strategy in self.underlying:
            strategy_symbols = strategy.get_symbols()
            for symbol in strategy_symbols:
                symbol_to_strategy_name[symbol] = strategy.name

        # Convert weights index from symbols to strategy names
        new_index = [symbol_to_strategy_name.get(symbols[i], symbols[i]) for i in weights.index]
        weights.index = new_index

        # Verify weights sum to 1.0 (within floating point precision)
        weight_sum = weights.sum()
        if not np.isclose(weight_sum, 1.0, atol=1e-6):
            # Normalize if needed (shouldn't be necessary, but safety check)
            weights = weights / weight_sum

        return weights

    def get_strategy_lookback(self) -> int:
        """
        HRP requires historical data for correlation calculation.

        Returns:
            252 (1 year of daily data for stable correlation estimates)
        """
        return 252
