"""
Data models for composable strategy system.

DEPRECATED: This module contains legacy data models from the old architecture.
The new unified Strategy interface uses StrategyContext and DataRequirements
from strategies.core instead.

New code should use:
  from strategies.core import StrategyContext, DataRequirements

This file is kept for backward compatibility only.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict
from datetime import datetime
import pandas as pd


@dataclass
class Instrument:
    """
    Single instrument specification for market definitions.

    DEPRECATED: Market definitions no longer exist in the new architecture.
    Use AssetStrategy instead for individual instruments.
    """

    symbol: str
    sec_type: str = "STK"
    exchange: str = "SMART"
    currency: str = "USD"

    def __repr__(self) -> str:
        return f"Instrument({self.symbol}, {self.currency})"


@dataclass
class MarketDefinition:
    """
    Complete specification of a market (asset universe).

    DEPRECATED: Market definitions no longer exist in the new architecture.
    Build portfolios directly as List[Strategy] instead.

    Example (old):
        market = UKETFsMarket()
        hrp = HRPStrategy(underlying=market)

    Example (new):
        assets = [AssetStrategy('VUSA'), AssetStrategy('SSLN'), ...]
        hrp = HRPStrategy(underlying=assets)
    """

    instruments: List[Instrument]
    name: str = "Custom Market"

    @property
    def symbols(self) -> List[str]:
        """Get list of symbols in this market."""
        return [inst.symbol for inst in self.instruments]

    def to_dict(self) -> Dict[str, Instrument]:
        """Convert to symbol -> Instrument mapping."""
        return {inst.symbol: inst for inst in self.instruments}


@dataclass
class OverlayContext:
    """
    Context provided to overlay strategies during transformation.

    DEPRECATED: Use StrategyContext from strategies.core instead.
    This class is no longer used in the new architecture.
    """

    current_date: datetime
    prices: pd.Series  # Current prices for all symbols
    underlying_portfolio_values: pd.Series  # Historical portfolio values from underlying
    lookback_window: int = 252
