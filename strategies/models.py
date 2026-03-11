"""
Data models for composable strategy system.

Provides data structures used across strategies, market definitions, and overlays.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict
from datetime import datetime
import pandas as pd


@dataclass
class Instrument:
    """Single instrument specification for market definitions."""

    symbol: str
    sec_type: str = "STK"
    exchange: str = "SMART"
    currency: str = "USD"

    def __repr__(self) -> str:
        return f"Instrument({self.symbol}, {self.currency})"


@dataclass
class MarketDefinition:
    """Complete specification of a market (asset universe)."""

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
    """Context provided to overlay strategies during transformation."""

    current_date: datetime
    prices: pd.Series  # Current prices for all symbols
    underlying_portfolio_values: pd.Series  # Historical portfolio values from underlying
    lookback_window: int = 252
