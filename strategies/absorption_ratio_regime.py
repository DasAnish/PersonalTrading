"""
Absorption Ratio Regime De-Risking (Kritzman et al. 2011).

PCA-based systemic risk detection: when the standardized shift in the
absorption ratio (fraction of return variance explained by top ~N/5 eigenvectors)
exceeds +1σ, markets are tightly coupled and diversification fails—shift to
defensive assets (VUTY, SGLN, AGGU). When AR shift drops below -1σ, full
risk-on allocation.

Reference: Kritzman, Li, Page & Rigobon (JPM 2011)
"Skulls, Financial Turbulence, and Risk Management"
"""

from __future__ import annotations

import logging
from typing import List, Optional

import numpy as np
import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class AbsorptionRatioRegimeStrategy(AllocationStrategy):
    """
    Absorption Ratio systemic-risk regime de-risking.

    Computes daily rolling absorption ratio (top K eigenvalues / total variance,
    K ≈ N/5) and measures its standardized shift. High positive shift indicates
    risk concentration and tight coupling—indicates defensive posture. Negative
    shift indicates diversification opportunity.
    """

    def __init__(
        self,
        underlying: List[Strategy],
        ar_short_days: int = 15,
        entry_z: float = 1.0,
        name: Optional[str] = None,
    ):
        """
        Args:
            underlying: List of underlying strategies/assets.
            ar_short_days: Window for short-term AR mean (default 15d).
            entry_z: Threshold in σ units (default 1.0).
            name: Display name.
        """
        super().__init__(
            underlying=underlying,
            name=name or f"Absorption Ratio Regime ({ar_short_days}d, z={entry_z})",
        )
        self.ar_short_days = ar_short_days
        self.entry_z = entry_z
        self.lookback_days = 504  # ~2 years for AR baseline

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        # Require sufficient history
        if len(prices) < self.lookback_days + 10:
            return self._equal_weight(prices)

        prices = prices.ffill(limit=3).dropna()
        if len(prices) < self.lookback_days:
            return self._equal_weight(prices)

        # Guard: need at least 10 assets for meaningful PCA
        if len(prices.columns) < 10:
            return self._equal_weight(prices)

        # Compute rolling AR series
        ar_series = self._compute_rolling_ar(prices)
        if ar_series is None or len(ar_series) < self.ar_short_days + 1:
            return self._equal_weight(prices)

        # Compute signal: standardized AR shift
        signal = self._compute_ar_signal(ar_series)

        logger.debug(
            f"ARRG: AR signal = {signal:.4f}, "
            f"entry_z threshold = {self.entry_z:.4f}"
        )

        # Determine posture
        symbol_to_name = self._build_name_map()
        all_symbols = list(prices.columns)
        index = [symbol_to_name.get(s, s) for s in all_symbols]
        weights = pd.Series(0.0, index=index)

        # Identify defensive assets available in prices
        defensive = [s for s in ["VUTY", "SGLN", "AGGU"] if s in prices.columns]
        if not defensive:
            # Fallback if none available
            defensive = [all_symbols[0]]

        # Identify risk assets
        risk_assets = [
            s for s in all_symbols if s not in defensive
        ]

        if signal > self.entry_z:
            # High AR shift → defensive posture
            logger.debug(f"ARRG: signal {signal:.4f} > {self.entry_z:.4f}, defensive posture")
            for sym in defensive:
                name = symbol_to_name.get(sym, sym)
                weights[name] = 1.0 / len(defensive)
        elif signal < -self.entry_z:
            # Low AR shift → full risk-on
            logger.debug(f"ARRG: signal {signal:.4f} < -{self.entry_z:.4f}, risk-on posture")
            for sym in risk_assets:
                name = symbol_to_name.get(sym, sym)
                weights[name] = 1.0 / len(risk_assets) if risk_assets else 0.0
        else:
            # Blend: 50/50 defensive and risk
            logger.debug(f"ARRG: signal {signal:.4f} in band, 50/50 blend")
            defensive_weight = 0.5 / len(defensive) if defensive else 0.0
            risk_weight = 0.5 / len(risk_assets) if risk_assets else 0.0
            for sym in defensive:
                name = symbol_to_name.get(sym, sym)
                weights[name] = defensive_weight
            for sym in risk_assets:
                name = symbol_to_name.get(sym, sym)
                weights[name] = risk_weight

        # Normalize to sum to 1
        total = weights.sum()
        if total > 0:
            weights /= total
        else:
            weights = self._equal_weight(prices)

        return weights

    def get_strategy_lookback(self) -> int:
        return self.lookback_days

    def _compute_rolling_ar(self, prices: pd.DataFrame) -> Optional[pd.Series]:
        """Compute rolling absorption ratio series."""
        returns = prices.pct_change().dropna()
        if len(returns) < 30:
            return None

        ar_values = []
        dates = []

        # Compute AR at each date using trailing 252d window
        for i in range(len(returns)):
            if i < 252:
                # Not enough history yet
                continue

            window_returns = returns.iloc[i - 252 : i + 1]
            if len(window_returns) < 30:
                continue

            try:
                # Compute correlation matrix
                corr_matrix = np.corrcoef(window_returns.T)

                # Ensure it's symmetric (handle numerical issues)
                corr_matrix = (corr_matrix + corr_matrix.T) / 2

                # Apply simple shrinkage toward identity: alpha * Sigma + (1-alpha) * I
                # alpha = 0.5 gives 50/50 blend toward identity
                n_assets = len(prices.columns)
                shrinkage_target = np.eye(n_assets)
                alpha = 0.6
                corr_matrix = alpha * corr_matrix + (1 - alpha) * shrinkage_target

                # Compute eigenvalues
                eigenvalues = np.linalg.eigvalsh(corr_matrix)
                eigenvalues = np.sort(eigenvalues)[::-1]  # Descending
                eigenvalues = np.maximum(eigenvalues, 0.0)  # Ensure non-negative

                # Top K = max(1, round(N/5))
                k = max(1, round(n_assets / 5))

                # Absorption ratio
                total_var = np.sum(eigenvalues)
                if total_var > 0:
                    ar = np.sum(eigenvalues[:k]) / total_var
                else:
                    ar = 1.0 / n_assets
                ar_values.append(ar)
                dates.append(returns.index[i])

            except Exception as e:
                logger.debug(f"AR computation failed at {returns.index[i]}: {e}")
                continue

        if not ar_values:
            return None

        return pd.Series(ar_values, index=dates)

    def _compute_ar_signal(self, ar_series: pd.Series) -> float:
        """Compute standardized AR shift."""
        if len(ar_series) < self.ar_short_days + 1:
            return 0.0

        mean_short = ar_series.iloc[-self.ar_short_days :].mean()
        mean_long = ar_series.iloc[-252:].mean() if len(ar_series) >= 252 else ar_series.mean()
        std_long = ar_series.iloc[-252:].std() if len(ar_series) >= 252 else ar_series.std()

        if std_long < 1e-6:  # Avoid division by zero
            return 0.0

        signal = (mean_short - mean_long) / std_long
        return signal

    def _build_name_map(self) -> dict:
        """Map symbols to strategy names."""
        symbol_to_name = {}
        for strategy in self.underlying:
            for sym in strategy.get_symbols():
                symbol_to_name[sym] = strategy.name
        return symbol_to_name

    def _equal_weight(self, prices: pd.DataFrame) -> pd.Series:
        """Equal-weight fallback."""
        symbol_to_name = self._build_name_map()
        index = [symbol_to_name.get(s, s) for s in prices.columns]
        return pd.Series(1.0 / len(prices.columns), index=index)
