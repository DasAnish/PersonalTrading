"""
Hierarchical Equal Risk Contribution (HERC) portfolio optimization strategy.

Implementation based on:
- Raffinot, T. (2018). "Hierarchical Equal Risk Contribution"
- Extends De Prado's HRP with equal risk contribution between clusters

HERC is similar to HRP but allocates risk EQUALLY between dendrogram branches
rather than using recursive bisection. This provides more balanced risk contribution
across the hierarchical structure.

Example:
    from strategies.core import AssetStrategy
    from strategies.herc import HERCStrategy
    from backtesting.engine import BacktestEngine

    # Create asset strategies
    assets = [
        AssetStrategy('VUSA', currency='GBP'),
        AssetStrategy('SSLN', currency='GBP'),
        AssetStrategy('SGLN', currency='GBP'),
        AssetStrategy('IWRD', currency='GBP'),
    ]

    # Create HERC strategy
    herc = HERCStrategy(underlying=assets, linkage_method='ward')

    # Run backtest
    engine = BacktestEngine(initial_capital=10000)
    results = await engine.run_backtest(herc, start_date, end_date)
"""

import warnings

import pandas as pd
import numpy as np
from scipy.cluster.hierarchy import linkage, ClusterWarning, dendrogram
from typing import List, Dict, Tuple

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
    if link is None or np.size(link) == 0:
        raise ValueError("Empty linkage matrix")

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


def get_herc_weights(
    cov: pd.DataFrame, link: np.ndarray, num_assets: int
) -> pd.Series:
    """
    Compute HERC weights via top-down recursive allocation with equal risk contribution.

    HERC allocates risk EQUALLY between the two branches at each dendrogram node:
    1. Start with all assets at the root
    2. At each node, divide the available risk 50/50 between left and right branches
      (based on the dendrogram structure from the linkage matrix)
    3. Recurse down to leaves
    4. Within final leaf clusters (single assets), weight by inverse variance

    Args:
        cov: Covariance matrix (DataFrame with index 0..num_assets-1)
        link: Linkage matrix from scipy.cluster.hierarchy.linkage()
              Shape (N-1, 4)
        num_assets: Number of original assets (N)

    Returns:
        pd.Series with index=asset_indices (0..N-1), values=portfolio weights
        Weights sum to 1.0
    """
    # Build dendrogram: tree of nested clusters indexed by linkage matrix
    # Each node in the tree can have:
    #   - id < num_assets: a leaf (individual asset)
    #   - id >= num_assets: a cluster (row id - num_assets in linkage matrix)

    # Start with risk allocation at the root (all assets)
    # Track which assets are in each recursive call
    weights = np.ones(num_assets)

    def allocate_herc(node_id: int, node_weight: float) -> None:
        """
        Recursively allocate weights top-down with equal risk contribution.

        Args:
            node_id: Cluster or asset ID (< num_assets = leaf, >= num_assets = cluster)
            node_weight: Total weight available for this node (starts at 1.0 at root)
        """
        if node_id < num_assets:
            # Leaf node: assign inverse-variance weight within its cluster
            # For a single asset in its own cluster, this is just its proportional share
            weights[node_id] = node_weight
        else:
            # Internal node: fetch left and right children from linkage matrix
            row_idx = int(node_id - num_assets)
            left_id = int(link[row_idx, 0])
            right_id = int(link[row_idx, 1])

            # Get the assets in each branch
            left_assets = get_cluster_assets(left_id, link, num_assets)
            right_assets = get_cluster_assets(right_id, link, num_assets)

            # Calculate variance of each branch using inverse-variance weights
            left_var = get_cluster_var(cov, left_assets)
            right_var = get_cluster_var(cov, right_assets)

            # HERC: Allocate weight inversely to variance (equal risk contribution)
            # Higher variance → lower weight
            total_var = left_var + right_var
            if total_var > 1e-10:
                left_weight = node_weight * (1 - left_var / total_var)
                right_weight = node_weight * (1 - right_var / total_var)
            else:
                # Fallback: equal split
                left_weight = node_weight / 2
                right_weight = node_weight / 2

            # Recurse to children
            allocate_herc(left_id, left_weight)
            allocate_herc(right_id, right_weight)

    def get_cluster_assets(node_id: int, link: np.ndarray, num_assets: int) -> List[int]:
        """
        Get all leaf asset indices under a given node in the dendrogram.

        Args:
            node_id: Cluster or asset ID
            link: Linkage matrix
            num_assets: Number of original assets

        Returns:
            List of asset indices (< num_assets) in this subtree
        """
        if node_id < num_assets:
            return [node_id]

        row_idx = int(node_id - num_assets)
        left_id = int(link[row_idx, 0])
        right_id = int(link[row_idx, 1])

        return get_cluster_assets(left_id, link, num_assets) + get_cluster_assets(
            right_id, link, num_assets
        )

    # Start allocation at the root (last row of linkage matrix)
    root_id = num_assets + len(link) - 1
    allocate_herc(root_id, 1.0)

    # Within each final cluster, apply inverse-variance weighting
    # For HERC, we further subdivide by inverse variance within leaves
    # Re-weight based on inverse variance within the final allocation

    # Get final inverse-variance scaling
    ivp = 1.0 / np.diag(cov.values)
    ivp = ivp / ivp.sum()

    # Combine: top-down allocation * inverse-variance within clusters
    weights = weights * ivp

    # Normalize to sum to 1.0
    weights = weights / weights.sum()

    return pd.Series(weights)


class HERCStrategy(AllocationStrategy):
    """
    Hierarchical Equal Risk Contribution (HERC) portfolio optimization strategy.

    HERC is a modern portfolio optimization technique that:
    - Uses hierarchical clustering on correlation matrix (like HRP)
    - Allocates risk EQUALLY between dendrogram branches (unlike HRP's bisection)
    - More balanced risk allocation across cluster hierarchy
    - Does not require matrix inversion (like HRP)

    Differences from HRP:
    - HRP: Recursive BISECTION (splits sorted assets in half by order)
    - HERC: Top-down EQUAL RISK CONTRIBUTION (splits at each node inversely to variance)

    The algorithm has three stages:
    1. Tree Clustering: Build hierarchical cluster tree from correlation matrix
    2. Equal Risk Contribution: Top-down allocation with equal risk split
    3. Inverse Variance: Final weighting within leaf clusters

    Example:
        assets = [
            AssetStrategy('VUSA', currency='GBP'),
            AssetStrategy('SSLN', currency='GBP'),
            AssetStrategy('SGLN', currency='GBP'),
            AssetStrategy('IWRD', currency='GBP'),
        ]
        herc = HERCStrategy(underlying=assets, linkage_method='ward')
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 252,
        linkage_method: str = "ward",
        name: str = None,
    ):
        """
        Initialize HERC strategy.

        Args:
            underlying: List of underlying strategies (assets or portfolios)
            lookback_days: Lookback window for correlation calculation (default 252)
            linkage_method: Linkage criterion for hierarchical clustering
                          'single' = nearest neighbor
                          'complete' = furthest neighbor
                          'average' = average distance
                          'ward' = minimize variance (default, recommended)
            name: Display name (default: "Hierarchical Equal Risk Contribution")
        """
        super().__init__(underlying, name=name or "Hierarchical Equal Risk Contribution")
        self.lookback_days = lookback_days
        self.linkage_method = linkage_method

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        """
        Calculate HERC portfolio weights from historical prices.

        Args:
            context: StrategyContext with prices and metadata
                    Prices must have sufficient history for correlation calculation
                    (default: 252 trading days)

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
                "HERC requires at least 2 assets. "
                f"Received {len(prices.columns)} assets."
            )

        if len(prices) < 30:
            raise ValueError(
                f"Insufficient data for HERC. "
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

        # Use most recent lookback_days of data
        lookback_prices = prices.iloc[-self.lookback_days:]

        # Calculate returns
        returns = lookback_prices.pct_change().dropna()

        # Calculate correlation matrix
        corr = returns.corr()

        if corr.isnull().any().any():
            raise ValueError(
                "Correlation matrix contains NaN values. This typically "
                "happens with degenerate or constant-price asset series "
                "(zero variance) over the lookback window."
            )

        # Convert correlation to distance matrix
        # Formula: d = sqrt(0.5 * (1 - corr))
        # Maps correlation [-1, 1] to distance [0, 1]
        d_corr = np.sqrt(0.5 * (1 - corr))

        # Perform hierarchical clustering
        # scipy emits a ClusterWarning because we pass a square (uncondensed)
        # distance matrix rather than a condensed vector. This is intentional
        # (matches the reference HERC implementation) and does not affect the
        # resulting weights, so we silence just that warning at the call site.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ClusterWarning)
            link = linkage(d_corr.values, method=self.linkage_method)

        # ===== Stage 2: Calculate Covariance and HERC Weights =====

        # Calculate covariance matrix from returns
        cov = returns.cov()

        # Calculate HERC weights using top-down equal risk contribution
        num_assets = len(prices.columns)
        weights = get_herc_weights(cov, link.copy(), num_assets)

        # Map from integer indices back to symbol/strategy names
        symbols = list(prices.columns)
        symbol_to_strategy_name = {}

        # Build mapping from symbol to strategy name
        for strategy in self.underlying:
            strategy_symbols = strategy.get_symbols()
            for symbol in strategy_symbols:
                symbol_to_strategy_name[symbol] = strategy.name

        # Convert weights index from symbol indices to strategy names
        new_index = [symbol_to_strategy_name.get(symbols[i], symbols[i]) for i in range(num_assets)]
        weights.index = new_index

        # Verify weights sum to 1.0 (within floating point precision)
        weight_sum = weights.sum()
        if not np.isclose(weight_sum, 1.0, atol=1e-6):
            # Normalize if needed (shouldn't be necessary, but safety check)
            weights = weights / weight_sum

        return weights

    def get_strategy_lookback(self) -> int:
        """
        HERC requires historical data for correlation calculation.

        Returns:
            lookback_days (default 252 - 1 year of daily data for stable correlation estimates)
        """
        return self.lookback_days
