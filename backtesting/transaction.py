"""
Transaction modeling for backtesting.

This module provides transaction data structures and cost calculation functions.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Transaction:
    """
    Represents a single transaction (buy or sell).

    Attributes:
        timestamp: When the transaction occurred
        symbol: Ticker symbol
        quantity: Number of shares (positive for buy, negative for sell)
        price: Price per share
        cost_bps: Transaction cost in basis points (100 bps = 1%)
        total_cost: Total transaction cost in currency units
    """

    timestamp: datetime
    symbol: str
    quantity: float
    price: float
    cost_bps: float
    total_cost: float

    @property
    def is_buy(self) -> bool:
        """Returns True if this is a buy transaction."""
        return self.quantity > 0

    @property
    def is_sell(self) -> bool:
        """Returns True if this is a sell transaction."""
        return self.quantity < 0

    @property
    def trade_value(self) -> float:
        """Returns the absolute value of the trade (quantity * price)."""
        return abs(self.quantity * self.price)

    def __repr__(self) -> str:
        action = "BUY" if self.is_buy else "SELL"
        return (
            f"Transaction({action} {abs(self.quantity):.0f} {self.symbol} "
            f"@ {self.price:.2f}, cost={self.total_cost:.2f})"
        )


def calculate_transaction_cost(
    quantity: float,
    price: float,
    cost_bps: float = 7.5
) -> float:
    """
    Calculate transaction cost for a trade.

    Transaction cost is calculated as a percentage of the trade value.

    Args:
        quantity: Number of shares (signed: positive=buy, negative=sell)
        price: Price per share
        cost_bps: Cost in basis points (default 7.5 bps = 0.075%)
                 100 bps = 1%

    Returns:
        Transaction cost in currency units (always positive)

    Example:
        >>> calculate_transaction_cost(100, 50.0, cost_bps=10.0)
        0.50  # 100 * 50 * 0.001 = 0.50
    """
    trade_value = abs(quantity * price)
    cost = trade_value * (cost_bps / 10000.0)
    return cost
