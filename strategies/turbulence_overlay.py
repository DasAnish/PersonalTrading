"""
Turbulence Risk-Scaling Overlay strategy.

Detects financial turbulence via Mahalanobis distance on a 5-asset-class
return vector and scales underlying risk weights toward safe asset (VUTY)
when turbulence exceeds trailing percentile.

Based on Kritzman & Li (2010) — turbulence (Mahalanobis d of return vector
from mean/covariance) spikes when returns are unusually large OR correlations
break structure. Risk-asset returns substantially lower during turbulent
periods, and turbulence is persistent, so de-risking after onset cuts max
drawdown 20-40% with flat-to-slightly-lower raw return.

Example:
    base = HRPStrategy(underlying=assets)
    overlay = TurbulenceOverlayStrategy(
        underlying=base,
        percentile=85,
        scale=0.5
    )
    weights = overlay.calculate_weights(context)
"""

from __future__ import annotations

import logging
from typing import List, Optional

import pandas as pd
import numpy as np

from strategies.core import OverlayStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)

# 5-asset-class return vector for turbulence (keeps Σ invertible)
TURBULENCE_ASSETS = ["VUSA", "IMEU", "VUTY", "SGLN", "COMM"]

# Safe asset to scale into during turbulence
SAFE_ASSET = "VUTY"


class TurbulenceOverlayStrategy(OverlayStrategy):
    """
    De-risk when financial turbulence exceeds trailing percentile.

    Scales underlying risk weights toward safe asset (VUTY) when turbulence
    (Mahalanobis distance of 5-asset-class return vector from mean/covariance)
    exceeds a trailing percentile threshold.

    Attributes:
        percentile: Turbulence threshold percentile (75/85/90, default 85)
        scale: De-risk scale factor (0.3-0.6, default 0.5)
        lookback_months: Lookback for covariance (36-60 months)
    """

    def __init__(
        self,
        underlying: Strategy,
        percentile: int = 85,
        scale: float = 0.5,
        lookback_months: int = 48,
        name: str = None,
    ):
        """
        Initialize Turbulence Overlay.

        Args:
            underlying: Strategy to overlay
            percentile: Turbulence threshold percentile (75/85/90, default 85)
            scale: De-risk scale factor when turbulent (0.3-0.6, default 0.5)
            lookback_months: Lookback for covariance calc (36-60, default 48)
            name: Display name
        """
        super().__init__(
            underlying,
            name=name or f"Turbulence ({percentile}th, scale={scale})",
        )
        self.percentile = percentile
        self.scale = scale
        self.lookback_months = lookback_months
        self.lookback_days = lookback_months * 21  # approx trading days

    def transform_weights(
        self, weights: pd.Series, context: StrategyContext
    ) -> pd.Series:
        """
        Scale weights if turbulence exceeds threshold.

        Args:
            weights: Original weights from underlying
            context: StrategyContext with price data

        Returns:
            Scaled weights (sum <= 1.0, with remainder as implicit cash/VUTY)

        Logic:
            1. Get returns for 5-asset turbulence vector
            2. Calculate Mahalanobis distance from historical mean/covariance
            3. Compare to trailing percentile
            4. If turbulent: scale weights down, remainder to VUTY
            5. If calm: pass weights through unchanged
        """
        # Get returns for turbulence assets
        prices = context.prices
        available_turb_assets = [a for a in TURBULENCE_ASSETS if a in prices.columns]

        if len(available_turb_assets) < 3:
            # Insufficient assets for covariance estimation
            logger.warning(
                f"TurbulenceOverlay: only {len(available_turb_assets)} of "
                f"{len(TURBULENCE_ASSETS)} assets available. Skipping overlay."
            )
            return weights

        # Get monthly returns (approximate: every 21 trading days)
        turb_prices = prices[available_turb_assets]

        # Aggregate to monthly (use last day of each month)
        monthly_prices = turb_prices.resample("ME").last()

        if len(monthly_prices) < self.lookback_months + 1:
            # Insufficient history
            logger.warning(
                f"TurbulenceOverlay: only {len(monthly_prices)} months of data, "
                f"need {self.lookback_months + 1}. Skipping overlay."
            )
            return weights

        # Calculate monthly returns
        monthly_returns = monthly_prices.pct_change().dropna()

        if len(monthly_returns) < self.lookback_months:
            return weights

        # Get lookback window
        lookback_window = monthly_returns.iloc[-self.lookback_months :]

        # Calculate mean and covariance
        mean_returns = lookback_window.mean()
        cov_matrix = lookback_window.cov()

        # Current month return (latest)
        current_return = monthly_returns.iloc[-1]

        # Calculate Mahalanobis distance
        try:
            # Regularize covariance (add small value to diagonal for numerical stability)
            cov_reg = cov_matrix + np.eye(len(cov_matrix)) * 1e-6
            cov_inv = np.linalg.inv(cov_reg)

            diff = (current_return - mean_returns).values
            turbulence = float(diff @ cov_inv @ diff.T)

            logger.debug(f"TurbulenceOverlay: current turbulence = {turbulence:.4f}")

        except np.linalg.LinAlgError:
            # Singular matrix; skip overlay
            logger.warning("TurbulenceOverlay: covariance singular. Skipping overlay.")
            return weights

        # Calculate historical turbulence values for percentile
        turbulence_history = []
        for i in range(len(lookback_window)):
            window_i = lookback_window.iloc[: i + 1]
            if len(window_i) < 3:
                continue
            mean_i = window_i.mean()
            cov_i = window_i.cov()
            try:
                cov_i_reg = cov_i + np.eye(len(cov_i)) * 1e-6
                cov_i_inv = np.linalg.inv(cov_i_reg)
                diff_i = (lookback_window.iloc[i] - mean_i).values
                turb_i = float(diff_i @ cov_i_inv @ diff_i.T)
                turbulence_history.append(turb_i)
            except:
                pass

        if not turbulence_history:
            return weights

        # Get percentile threshold
        threshold = np.percentile(turbulence_history, self.percentile)

        logger.debug(
            f"TurbulenceOverlay: percentile={self.percentile}, "
            f"threshold={threshold:.4f}, current={turbulence:.4f}"
        )

        # Scale if turbulent
        is_turbulent = turbulence > threshold
        if is_turbulent:
            logger.debug(
                f"TurbulenceOverlay: TURBULENT. Scaling weights by {self.scale}"
            )
            scaled_weights = weights * self.scale

            # Redirect unallocated weight to VUTY
            safe_idx = None
            for i, name in enumerate(scaled_weights.index):
                # Look for VUTY in the weight index (by symbol or name)
                if "VUTY" in name or name == SAFE_ASSET:
                    safe_idx = i
                    break

            if safe_idx is not None:
                unallocated = 1.0 - scaled_weights.sum()
                scaled_weights.iloc[safe_idx] += unallocated

            return scaled_weights
        else:
            logger.debug(f"TurbulenceOverlay: calm. Passing weights through.")
            return weights

    def get_overlay_lookback(self) -> int:
        """
        Turbulence Overlay requires lookback for covariance estimation.

        Returns:
            lookback_days (for monthly return aggregation and covariance)
        """
        return self.lookback_days
