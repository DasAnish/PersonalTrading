"""
Backtesting engine for portfolio strategies.

This module provides the core backtesting simulation engine that runs
portfolio strategies on historical data.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict
import pandas as pd
import logging

from strategies.base import BaseStrategy
from .portfolio_state import PortfolioState
from .transaction import Transaction

logger = logging.getLogger(__name__)


@dataclass
class BacktestResults:
    """
    Results from a backtest run.

    Attributes:
        strategy_name: Name of the strategy tested
        portfolio_history: DataFrame with columns: timestamp, cash, total_value, position columns
        weights_history: DataFrame with columns=symbols, index=dates, values=weights at each rebalance
        transactions: List of all transactions executed
        metrics: Dict of performance metrics
        initial_capital: Starting capital
        final_value: Ending portfolio value
    """

    strategy_name: str
    portfolio_history: pd.DataFrame
    weights_history: pd.DataFrame
    transactions: List[Transaction]
    metrics: Dict[str, float] = field(default_factory=dict)
    initial_capital: float = 0.0
    final_value: float = 0.0


class BacktestEngine:
    """
    Backtesting simulation engine.

    Simulates portfolio strategy execution over historical data with:
    - Monthly (or custom frequency) rebalancing
    - Transaction costs
    - Portfolio state tracking
    - Performance metrics calculation
    """

    def __init__(
        self,
        initial_capital: float,
        transaction_cost_bps: float = 7.5,
        rebalance_frequency: str = 'monthly',
        lookback_days: int = 252
    ):
        """
        Initialize backtest engine.

        Args:
            initial_capital: Starting capital in currency units
            transaction_cost_bps: Transaction cost in basis points (default 7.5 bps)
            rebalance_frequency: How often to rebalance ('monthly', 'weekly', 'quarterly')
            lookback_days: Number of days of data to use for strategy calculation (default 252 = 1 year)
        """
        self.initial_capital = initial_capital
        self.transaction_cost_bps = transaction_cost_bps
        self.rebalance_frequency = rebalance_frequency
        self.lookback_days = lookback_days

    def run_backtest(
        self,
        strategy: BaseStrategy,
        historical_data: pd.DataFrame,
        start_date: datetime = None,
        end_date: datetime = None
    ) -> BacktestResults:
        """
        Run backtest simulation.

        Args:
            strategy: Strategy instance implementing BaseStrategy
            historical_data: DataFrame with columns=symbols, index=dates, values=prices
                           Must have sufficient history for lookback_days before start_date
            start_date: Start date for backtest (default: first valid date after lookback)
            end_date: End date for backtest (default: last date in data)

        Returns:
            BacktestResults with portfolio history, transactions, and metrics

        Raises:
            ValueError: If insufficient data or invalid date range
        """
        logger.info(f"Starting backtest for strategy: {strategy.name}")

        # Validate input
        if historical_data.empty:
            raise ValueError("Historical data is empty")

        # Set default date range
        if start_date is None:
            # Start after we have enough lookback data
            if len(historical_data) <= self.lookback_days:
                raise ValueError(
                    f"Insufficient data. Need at least {self.lookback_days} days "
                    f"before backtest start. Have {len(historical_data)} days total."
                )
            start_date = historical_data.index[self.lookback_days]

        if end_date is None:
            end_date = historical_data.index[-1]

        # Filter data to backtest period
        backtest_data = historical_data[
            (historical_data.index >= start_date) &
            (historical_data.index <= end_date)
        ]

        if backtest_data.empty:
            raise ValueError(f"No data in date range {start_date} to {end_date}")

        logger.info(
            f"Backtest period: {start_date.date()} to {end_date.date()} "
            f"({len(backtest_data)} days)"
        )

        # Generate rebalance dates
        rebalance_dates = self._generate_rebalance_dates(
            start_date,
            end_date,
            backtest_data.index
        )

        logger.info(f"Will rebalance {len(rebalance_dates)} times")

        # Initialize portfolio state
        portfolio = PortfolioState(
            timestamp=start_date,
            cash=self.initial_capital,
            positions={},
            prices={}
        )

        # Track history
        portfolio_history = []
        weights_history = []
        all_transactions = []

        # Record initial state
        portfolio_history.append(self._record_state(portfolio, backtest_data.loc[start_date]))

        # Run backtest
        for rebalance_date in rebalance_dates:
            try:
                # Get lookback window for strategy calculation
                lookback_data = self._get_lookback_data(
                    historical_data,
                    rebalance_date,
                    self.lookback_days
                )

                if lookback_data.empty or len(lookback_data) < 30:
                    logger.warning(
                        f"Insufficient lookback data at {rebalance_date.date()}, skipping"
                    )
                    continue

                # Calculate strategy weights
                weights = strategy.calculate_weights(lookback_data)

                # Record weights at this rebalance date
                weight_record = {'timestamp': rebalance_date}
                weight_record.update(weights.to_dict())
                weights_history.append(weight_record)

                # Get current prices
                current_prices = backtest_data.loc[rebalance_date]

                # Update portfolio timestamp
                portfolio.timestamp = rebalance_date

                # Execute rebalance
                transactions = portfolio.execute_rebalance(
                    target_weights=weights,
                    prices=current_prices,
                    transaction_cost_bps=self.transaction_cost_bps
                )

                all_transactions.extend(transactions)

                # Record state after rebalance
                portfolio_history.append(self._record_state(portfolio, current_prices))

                logger.debug(
                    f"Rebalanced at {rebalance_date.date()}: "
                    f"value={portfolio.total_value():.2f}, "
                    f"transactions={len(transactions)}"
                )

            except Exception as e:
                logger.error(f"Error at rebalance date {rebalance_date.date()}: {e}")
                continue

        # Convert history to DataFrame
        history_df = pd.DataFrame(portfolio_history)
        history_df.set_index('timestamp', inplace=True)

        # Convert weights history to DataFrame
        if weights_history:
            weights_df = pd.DataFrame(weights_history)
            weights_df.set_index('timestamp', inplace=True)
        else:
            # Empty DataFrame with proper structure if no rebalances
            weights_df = pd.DataFrame()

        # Calculate final value
        final_value = portfolio.total_value()

        logger.info(
            f"Backtest complete: "
            f"Initial={self.initial_capital:.2f}, "
            f"Final={final_value:.2f}, "
            f"Return={(final_value/self.initial_capital - 1)*100:.2f}%"
        )

        # Create results object
        results = BacktestResults(
            strategy_name=strategy.name,
            portfolio_history=history_df,
            weights_history=weights_df,
            transactions=all_transactions,
            initial_capital=self.initial_capital,
            final_value=final_value
        )

        return results

    def run_backtest_with_overlay(
        self,
        underlying_strategy: 'BaseStrategy',
        overlay_strategy: 'BaseStrategy',
        historical_data: pd.DataFrame,
        underlying_results: BacktestResults,
        start_date: datetime = None,
        end_date: datetime = None
    ) -> BacktestResults:
        """
        Run backtest with overlay strategy transformations.

        This method runs the backtest where at each rebalance, weights from the
        underlying strategy are transformed by the overlay strategy. This enables
        overlays like volatility targeting on top of any allocation strategy.

        Args:
            underlying_strategy: Base allocation strategy (e.g., HRP)
            overlay_strategy: Overlay strategy that transforms weights
            historical_data: DataFrame with columns=symbols, index=dates, values=prices
            underlying_results: Results from running underlying strategy
            start_date: Start date for backtest (default: first valid date after lookback)
            end_date: End date for backtest (default: last date in data)

        Returns:
            BacktestResults with overlay-transformed portfolio history
        """
        logger.info(f"Starting overlay backtest: {overlay_strategy.name} > {underlying_strategy.name}")

        # Validate input
        if historical_data.empty:
            raise ValueError("Historical data is empty")

        # Set default date range
        if start_date is None:
            if len(historical_data) <= self.lookback_days:
                raise ValueError(
                    f"Insufficient data. Need at least {self.lookback_days} days "
                    f"before backtest start. Have {len(historical_data)} days total."
                )
            start_date = historical_data.index[self.lookback_days]

        if end_date is None:
            end_date = historical_data.index[-1]

        # Filter data to backtest period
        backtest_data = historical_data[
            (historical_data.index >= start_date) &
            (historical_data.index <= end_date)
        ]

        if backtest_data.empty:
            raise ValueError(f"No data in date range {start_date} to {end_date}")

        logger.info(
            f"Backtest period: {start_date.date()} to {end_date.date()} "
            f"({len(backtest_data)} days)"
        )

        # Generate rebalance dates
        rebalance_dates = self._generate_rebalance_dates(
            start_date,
            end_date,
            backtest_data.index
        )

        logger.info(f"Will rebalance {len(rebalance_dates)} times with overlay")

        # Get underlying portfolio values for overlay context
        underlying_portfolio_values = underlying_results.portfolio_history['total_value']

        # Initialize portfolio state
        portfolio = PortfolioState(
            timestamp=start_date,
            cash=self.initial_capital,
            positions={},
            prices={}
        )

        # Track history
        portfolio_history = []
        weights_history = []
        all_transactions = []

        # Record initial state
        portfolio_history.append(self._record_state(portfolio, backtest_data.loc[start_date]))

        # Run backtest with overlay
        for rebalance_date in rebalance_dates:
            try:
                # Get lookback window for strategy calculation
                lookback_data = self._get_lookback_data(
                    historical_data,
                    rebalance_date,
                    self.lookback_days
                )

                if lookback_data.empty or len(lookback_data) < 30:
                    logger.warning(
                        f"Insufficient lookback data at {rebalance_date.date()}, skipping"
                    )
                    continue

                # Calculate underlying strategy weights
                underlying_weights = underlying_strategy.calculate_weights(lookback_data)

                # Get current prices for overlay context
                current_prices = backtest_data.loc[rebalance_date]

                # Create overlay context with underlying portfolio values
                from strategies.models import OverlayContext
                context = OverlayContext(
                    current_date=rebalance_date,
                    prices=current_prices,
                    underlying_portfolio_values=underlying_portfolio_values,
                    lookback_window=self.lookback_days
                )

                # Transform weights using overlay
                overlay_weights = overlay_strategy.transform_weights(underlying_weights, context)

                # Record weights at this rebalance date
                weight_record = {'timestamp': rebalance_date}
                weight_record.update(overlay_weights.to_dict())
                weights_history.append(weight_record)

                # Update portfolio timestamp
                portfolio.timestamp = rebalance_date

                # Execute rebalance with transformed weights
                transactions = portfolio.execute_rebalance(
                    target_weights=overlay_weights,
                    prices=current_prices,
                    transaction_cost_bps=self.transaction_cost_bps
                )

                all_transactions.extend(transactions)

                # Record state after rebalance
                portfolio_history.append(self._record_state(portfolio, current_prices))

                logger.debug(
                    f"Rebalanced at {rebalance_date.date()}: "
                    f"value={portfolio.total_value():.2f}, "
                    f"transactions={len(transactions)}"
                )

            except Exception as e:
                logger.error(f"Error at rebalance date {rebalance_date.date()}: {e}")
                continue

        # Convert history to DataFrame
        history_df = pd.DataFrame(portfolio_history)
        history_df.set_index('timestamp', inplace=True)

        # Convert weights history to DataFrame
        if weights_history:
            weights_df = pd.DataFrame(weights_history)
            weights_df.set_index('timestamp', inplace=True)
        else:
            weights_df = pd.DataFrame()

        # Calculate final value
        final_value = portfolio.total_value()

        logger.info(
            f"Overlay backtest complete: "
            f"Initial={self.initial_capital:.2f}, "
            f"Final={final_value:.2f}, "
            f"Return={(final_value/self.initial_capital - 1)*100:.2f}%"
        )

        # Create results object
        results = BacktestResults(
            strategy_name=f"{overlay_strategy.name} > {underlying_strategy.name}",
            portfolio_history=history_df,
            weights_history=weights_df,
            transactions=all_transactions,
            initial_capital=self.initial_capital,
            final_value=final_value
        )

        return results

    def _generate_rebalance_dates(
        self,
        start_date: datetime,
        end_date: datetime,
        available_dates: pd.DatetimeIndex
    ) -> List[datetime]:
        """
        Generate rebalance dates based on frequency.

        Args:
            start_date: Start of backtest
            end_date: End of backtest
            available_dates: Available trading dates in data

        Returns:
            List of rebalance dates
        """
        # Map frequency to pandas offset
        freq_map = {
            'monthly': 'ME',
            'weekly': 'W',
            'quarterly': 'QE',
            'daily': 'D'
        }

        freq = freq_map.get(self.rebalance_frequency.lower(), 'M')

        # Generate candidate dates
        candidate_dates = pd.date_range(
            start=start_date,
            end=end_date,
            freq=freq
        )

        # Align to actual trading days (find nearest following trading day)
        rebalance_dates = []
        for date in candidate_dates:
            # Find nearest trading day on or after this date
            future_dates = available_dates[available_dates >= date]
            if len(future_dates) > 0:
                rebalance_dates.append(future_dates[0])

        return rebalance_dates

    def _get_lookback_data(
        self,
        data: pd.DataFrame,
        rebalance_date: datetime,
        lookback_days: int
    ) -> pd.DataFrame:
        """
        Get lookback window of data for strategy calculation.

        Args:
            data: Full historical data
            rebalance_date: Current rebalance date
            lookback_days: Number of days to look back

        Returns:
            DataFrame with lookback_days of data ending at rebalance_date
        """
        # Get all dates up to and including rebalance date
        available_dates = data.index[data.index <= rebalance_date]

        if len(available_dates) < lookback_days:
            # Not enough history - return what we have
            return data.loc[:rebalance_date]

        # Get last lookback_days of data
        start_idx = len(available_dates) - lookback_days
        start_date = available_dates[start_idx]

        return data.loc[start_date:rebalance_date]

    def _record_state(
        self,
        portfolio: PortfolioState,
        prices: pd.Series
    ) -> Dict:
        """
        Record portfolio state as a dictionary for history tracking.

        Args:
            portfolio: Current portfolio state
            prices: Current prices

        Returns:
            Dict with timestamp, cash, total_value, and position values
        """
        record = {
            'timestamp': portfolio.timestamp,
            'cash': portfolio.cash,
            'total_value': portfolio.total_value()
        }

        # Add position values
        for symbol, qty in portfolio.positions.items():
            price = prices.get(symbol, portfolio.prices.get(symbol, 0.0))
            record[f'{symbol}_qty'] = qty
            record[f'{symbol}_value'] = qty * price

        return record
