"""
Backtesting engine for portfolio strategies (refactored for new architecture).

This module provides the core backtesting simulation engine that works with
the new unified Strategy interface. The engine:
- Works with any Strategy (assets, allocations, overlays, meta-portfolios)
- Delegates data management to MarketData singleton
- Focuses purely on portfolio simulation and trade execution

Key change from old architecture:
- Strategies no longer receive raw DataFrames
- Engine gets StrategyContext from singleton for each date
- No lookback window calculations in engine (singleton handles this)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict
import pandas as pd
import logging

from strategies.core import Strategy, StrategyContext
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
    Backtesting simulation engine for new composable strategy architecture.

    Simulates portfolio strategy execution with:
    - Monthly (or custom frequency) rebalancing
    - Transaction costs
    - Portfolio state tracking
    - Support for any Strategy type (assets, allocations, overlays, meta-portfolios)

    Data management is delegated to MarketDataService singleton, keeping the
    engine focused on pure portfolio simulation.

    Example:
        from datetime import datetime
        from data import get_market_data
        from strategies import AssetStrategy, HRPStrategy
        from ib_wrapper.client import IBClient

        # Initialize
        async with IBClient(...) as client:
            mds = get_market_data()
            mds.configure(client, 'data/cache')

            engine = BacktestEngine(initial_capital=10000)

            # Create and run strategy
            assets = [
                AssetStrategy('VUSA', currency='GBP'),
                AssetStrategy('SSLN', currency='GBP'),
            ]
            strategy = HRPStrategy(underlying=assets)

            results = engine.run_backtest(
                strategy=strategy,
                start_date=datetime(2020, 1, 1),
                end_date=datetime(2024, 1, 1),
                refresh=False
            )
    """

    def __init__(
        self,
        initial_capital: float,
        transaction_cost_bps: float = 7.5,
        rebalance_frequency: str = 'monthly'
    ):
        """
        Initialize backtest engine.

        Args:
            initial_capital: Starting capital in currency units
            transaction_cost_bps: Transaction cost in basis points (default 7.5 bps)
            rebalance_frequency: How often to rebalance ('monthly', 'weekly', 'quarterly', 'daily')
        """
        self.initial_capital = initial_capital
        self.transaction_cost_bps = transaction_cost_bps
        self.rebalance_frequency = rebalance_frequency

    async def run_backtest(
        self,
        strategy: Strategy,
        start_date: datetime,
        end_date: datetime,
        refresh: bool = False
    ) -> BacktestResults:
        """
        Run backtest simulation for any strategy (async).

        Data fetching and lookback window management are handled by
        the MarketData singleton based on strategy's DataRequirements.

        Args:
            strategy: Any Strategy instance (asset, allocation, overlay, meta-portfolio)
            start_date: Start date for backtest period
            end_date: End date for backtest period
            refresh: If True, force fresh data fetch from IB (skip cache)

        Returns:
            BacktestResults with portfolio history, transactions, and metrics

        Raises:
            ValueError: If insufficient data or invalid date range
            RuntimeError: If MarketData singleton not configured
        """
        from data import get_market_data

        logger.info(f"Starting backtest for strategy: {strategy.name}")

        # Get MarketData singleton
        mds = get_market_data()

        # Fetch data based on strategy's requirements
        # Singleton handles all lookback calculations
        requirements = strategy.get_data_requirements()
        all_data = await mds.fetch_data(
            requirements=requirements,
            start_date=start_date,
            end_date=end_date,
            refresh=refresh
        )

        if all_data.empty:
            raise ValueError("No data available for backtest")

        logger.info(
            f"Fetched {len(all_data)} trading days for {len(all_data.columns)} symbols"
        )

        # Filter to backtest period
        backtest_data = all_data[
            (all_data.index >= start_date) &
            (all_data.index <= end_date)
        ]

        if backtest_data.empty:
            raise ValueError(f"No data in backtest period {start_date} to {end_date}")

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
                # Get strategy context for this date (singleton handles lookback slicing)
                context = mds.get_context_for_date(
                    all_data=all_data,
                    current_date=rebalance_date,
                    lookback_days=requirements.lookback_days
                )

                # Strategy calculates weights from context
                # Context has pre-sliced data, strategy never sees full history
                weights = strategy.calculate_weights(context)

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
            List of rebalance dates aligned to trading days
        """
        # Map frequency to pandas offset
        freq_map = {
            'monthly': 'ME',
            'weekly': 'W',
            'quarterly': 'QE',
            'daily': 'D'
        }

        freq = freq_map.get(self.rebalance_frequency.lower(), 'ME')

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
