"""
Portfolio state tracking for backtesting.

This module provides portfolio state management and rebalancing logic.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List
import pandas as pd

from .transaction import Transaction, calculate_transaction_cost


@dataclass
class PortfolioState:
    """
    Represents the state of a portfolio at a point in time.

    Attributes:
        timestamp: Current datetime
        cash: Available cash
        positions: Dict mapping symbol to quantity held
        prices: Dict mapping symbol to current price
    """

    timestamp: datetime
    cash: float
    positions: Dict[str, float] = field(default_factory=dict)
    prices: Dict[str, float] = field(default_factory=dict)

    def total_value(self) -> float:
        """
        Calculate total portfolio value (cash + positions).

        Returns:
            Total portfolio value in currency units
        """
        positions_value = sum(
            qty * self.prices.get(symbol, 0.0)
            for symbol, qty in self.positions.items()
        )
        return self.cash + positions_value

    def positions_value(self) -> Dict[str, float]:
        """
        Calculate value of each position.

        Returns:
            Dict mapping symbol to position value (quantity * price)
        """
        return {
            symbol: qty * self.prices.get(symbol, 0.0)
            for symbol, qty in self.positions.items()
        }

    def execute_rebalance(
        self,
        target_weights: pd.Series,
        prices: pd.Series,
        transaction_cost_bps: float = 7.5
    ) -> List[Transaction]:
        """
        Execute a portfolio rebalance to achieve target weights.

        This method:
        1. Calculates target units for each symbol
        2. Generates transactions to move from current to target positions
        3. Calculates and deducts transaction costs
        4. Updates portfolio state (cash and positions)

        Args:
            target_weights: Series with index=symbols, values=target weights (sum to 1.0)
            prices: Series with index=symbols, values=current prices
            transaction_cost_bps: Transaction cost in basis points

        Returns:
            List of Transaction objects executed

        Raises:
            ValueError: If insufficient cash to execute rebalance
        """
        # Get current portfolio value
        net_value = self.total_value()

        # Calculate target units: (net_value * weight) / price
        target_units = {}
        for symbol in target_weights.index:
            if symbol in prices.index and prices[symbol] > 0:
                target_value = net_value * target_weights[symbol]
                target_units[symbol] = target_value / prices[symbol]
            else:
                target_units[symbol] = 0.0

        # Round to whole shares
        target_units = {symbol: round(units) for symbol, units in target_units.items()}

        # Generate transactions: target - current
        transactions = []
        total_cost = 0.0

        for symbol in target_weights.index:
            current_qty = self.positions.get(symbol, 0.0)
            target_qty = target_units[symbol]
            trade_qty = target_qty - current_qty

            if abs(trade_qty) < 0.5:
                # Skip trades smaller than 0.5 shares (rounding tolerance)
                continue

            price = prices[symbol]

            # Calculate transaction cost
            cost = calculate_transaction_cost(trade_qty, price, transaction_cost_bps)
            total_cost += cost

            # Create transaction record
            transaction = Transaction(
                timestamp=self.timestamp,
                symbol=symbol,
                quantity=trade_qty,
                price=price,
                cost_bps=transaction_cost_bps,
                total_cost=cost
            )
            transactions.append(transaction)

            # Update positions
            self.positions[symbol] = target_qty

        # Deduct transaction costs from cash
        if total_cost > self.cash:
            # Insufficient cash - need to scale down trades
            # This is a simplified approach; in practice, you might want more sophisticated logic
            scale_factor = (self.cash * 0.99) / total_cost if total_cost > 0 else 1.0

            # Re-calculate with scaled trades
            transactions = []
            total_cost = 0.0

            for symbol in target_weights.index:
                current_qty = self.positions.get(symbol, 0.0)
                target_qty = target_units[symbol]
                trade_qty = (target_qty - current_qty) * scale_factor

                if abs(trade_qty) < 0.5:
                    continue

                trade_qty = round(trade_qty)
                price = prices[symbol]

                cost = calculate_transaction_cost(trade_qty, price, transaction_cost_bps)
                total_cost += cost

                transaction = Transaction(
                    timestamp=self.timestamp,
                    symbol=symbol,
                    quantity=trade_qty,
                    price=price,
                    cost_bps=transaction_cost_bps,
                    total_cost=cost
                )
                transactions.append(transaction)

                # Update positions with scaled trade
                self.positions[symbol] = current_qty + trade_qty

        # Calculate cash impact: -sum(quantity * price) - costs
        cash_impact = sum(t.quantity * t.price for t in transactions)
        self.cash -= (cash_impact + total_cost)

        # Update prices
        self.prices = prices.to_dict()

        return transactions

    def copy(self) -> 'PortfolioState':
        """
        Create a copy of this portfolio state.

        Returns:
            New PortfolioState with copied attributes
        """
        return PortfolioState(
            timestamp=self.timestamp,
            cash=self.cash,
            positions=self.positions.copy(),
            prices=self.prices.copy()
        )

    def __repr__(self) -> str:
        return (
            f"PortfolioState(value={self.total_value():.2f}, "
            f"cash={self.cash:.2f}, positions={len(self.positions)})"
        )
