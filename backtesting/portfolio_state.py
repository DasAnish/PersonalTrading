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

        # CRITICAL: Save original positions before any updates
        # This is needed for the insufficient cash recovery path to work correctly
        original_positions = self.positions.copy()

        # Generate transactions: target - current
        transactions = []
        total_cost = 0.0
        total_buy_cost = 0.0  # Track total cost of buys (excluding costs, which are paid separately)

        for symbol in target_weights.index:
            current_qty = original_positions.get(symbol, 0.0)
            target_qty = target_units[symbol]
            trade_qty = target_qty - current_qty

            if abs(trade_qty) < 0.5:
                # Skip trades smaller than 0.5 shares (rounding tolerance)
                continue

            price = prices[symbol]

            # Calculate transaction cost
            cost = calculate_transaction_cost(trade_qty, price, transaction_cost_bps)
            total_cost += cost

            # Track cost of buys (positive trade_qty * price)
            if trade_qty > 0:
                total_buy_cost += trade_qty * price

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

        # Check if we have enough cash for all trades (buys cost cash + transaction costs)
        # Sells generate cash, so net cash needed = buys - sells + costs
        net_cash_needed = sum(t.quantity * t.price for t in transactions if t.quantity > 0)
        net_cash_available = self.cash + sum(-t.quantity * t.price for t in transactions if t.quantity < 0)

        if net_cash_needed + total_cost > net_cash_available:
            # Insufficient cash - need to scale down buys
            # Strategy: Execute all sells first to raise cash, then scale down buys

            # Restore original positions before recalculating
            self.positions = original_positions.copy()

            # Recalculate with sells prioritized
            transactions = []
            total_cost = 0.0

            # First pass: execute all sells
            for symbol in target_weights.index:
                current_qty = original_positions.get(symbol, 0.0)
                target_qty = target_units[symbol]
                trade_qty = target_qty - current_qty

                # Only process sells in first pass
                if trade_qty >= -0.5:
                    continue

                price = prices[symbol]
                trade_qty = round(trade_qty)

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
                self.positions[symbol] = current_qty + trade_qty

            # Calculate available cash after sells
            sell_proceeds = sum(-t.quantity * t.price for t in transactions)
            available_for_buys = self.cash + sell_proceeds - total_cost

            # Second pass: scale down buys based on available cash
            buy_transactions = []
            buy_cost = 0.0

            for symbol in target_weights.index:
                current_qty = self.positions.get(symbol, 0.0)
                target_qty = target_units[symbol]
                trade_qty = target_qty - current_qty

                # Only process buys in second pass
                if trade_qty < 0.5:
                    continue

                price = prices[symbol]

                # Scale down the buy if needed
                if buy_cost + (trade_qty * price) <= available_for_buys:
                    scaled_qty = round(trade_qty)
                    buy_cost += trade_qty * price
                else:
                    # Scale this buy and skip remaining buys
                    remaining_cash = available_for_buys - buy_cost
                    if remaining_cash > price:
                        scaled_qty = round(remaining_cash / price)
                    else:
                        scaled_qty = 0

                if abs(scaled_qty) < 0.5:
                    continue

                cost = calculate_transaction_cost(scaled_qty, price, transaction_cost_bps)
                total_cost += cost

                transaction = Transaction(
                    timestamp=self.timestamp,
                    symbol=symbol,
                    quantity=scaled_qty,
                    price=price,
                    cost_bps=transaction_cost_bps,
                    total_cost=cost
                )
                buy_transactions.append(transaction)
                self.positions[symbol] = current_qty + scaled_qty

            transactions.extend(buy_transactions)

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
