"""
Cross-Asset Time-Series Momentum strategy.

Based on Pitkäjärvi, Suominen & Vaittinen (2020), "Cross-asset signals and
time series momentum", Journal of Financial Economics: past 12-month bond
returns positively predict equity returns, while past equity returns
negatively predict bond returns. Equity exposure therefore requires both
the asset's own trend and bond-market confirmation; bond exposure follows
its own trend but is only halved (never zeroed) when negative, keeping the
portfolio long-only and always invested.
"""

import logging
from typing import List

import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)


class CrossAssetTSMStrategy(AllocationStrategy):
    """
    Cross-asset TSM allocation.

    1. Bond signal = sign of mean trailing ``lookback_days`` return across
       ``bond_symbols`` present in the price frame.
    2. Equity (non-bond) assets: exposure 1.0 when own trend and bond signal
       are both positive; 0.5 when exactly one is; 0.0 otherwise.
    3. Bond assets: exposure 1.0 when own trend positive, else 0.5.
    4. Weights proportional to exposure / trailing ``vol_window_days`` vol,
       normalised to 1; if all exposures are zero, equal-weight the
       defensive assets present (``defensive_symbols``).
    """

    def __init__(
        self,
        underlying: List[Strategy],
        lookback_days: int = 252,
        vol_window_days: int = 63,
        bond_symbols: List[str] = None,
        defensive_symbols: List[str] = None,
        name: str = None,
    ):
        super().__init__(underlying, name=name or "Cross-Asset TSM")
        self.lookback_days = lookback_days
        self.vol_window_days = vol_window_days
        self.bond_symbols = bond_symbols or ["VUTY", "AGGU", "SEGA", "HYLD", "SAEM"]
        self.defensive_symbols = defensive_symbols or ["VUTY", "SGLN"]

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        prices = context.prices

        if prices.empty or len(prices.columns) < 2:
            raise ValueError("Cross-Asset TSM requires at least 2 assets.")

        min_required = max(self.lookback_days, self.vol_window_days) + 10
        if len(prices) < min_required:
            raise ValueError(
                f"Insufficient data for cross-asset TSM: "
                f"{len(prices)} < {min_required}"
            )

        prices = prices.ffill(limit=3).dropna()

        window = prices.iloc[-self.lookback_days :]
        own_ret = window.iloc[-1] / window.iloc[0] - 1

        bonds_present = [s for s in self.bond_symbols if s in prices.columns]
        if not bonds_present:
            logger.warning(
                "Cross-Asset TSM: no bond symbols in universe, "
                "falling back to own-trend only."
            )
            bond_positive = True
        else:
            bond_positive = own_ret[bonds_present].mean() > 0

        exposure = pd.Series(0.0, index=prices.columns)
        for symbol in prices.columns:
            own_positive = own_ret[symbol] > 0
            if symbol in bonds_present:
                exposure[symbol] = 1.0 if own_positive else 0.5
            else:
                exposure[symbol] = (int(own_positive) + int(bond_positive)) / 2.0

        symbol_to_name = self._build_name_map()
        index = [symbol_to_name.get(s, s) for s in prices.columns]

        if exposure.sum() == 0:
            defensive = [s for s in self.defensive_symbols if s in prices.columns]
            targets = defensive or list(prices.columns)
            weights = pd.Series(0.0, index=index)
            for symbol in targets:
                weights[symbol_to_name.get(symbol, symbol)] = 1.0 / len(targets)
            return weights

        vol_returns = prices.iloc[-self.vol_window_days :].pct_change().dropna()
        vols = vol_returns.std()
        vols[vols == 0] = 1e-10

        raw = exposure / vols
        raw = raw / raw.sum()

        weights = pd.Series(0.0, index=index)
        for symbol in prices.columns:
            weights[symbol_to_name.get(symbol, symbol)] = raw[symbol]
        return weights

    def _build_name_map(self) -> dict:
        symbol_to_name = {}
        for strategy in self.underlying:
            for symbol in strategy.get_symbols():
                symbol_to_name[symbol] = strategy.name
        return symbol_to_name

    def get_strategy_lookback(self) -> int:
        return max(self.lookback_days, self.vol_window_days) + 10
