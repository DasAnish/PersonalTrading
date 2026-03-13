"""
Parameter sweep engine for strategy optimization.

Runs backtests across all combinations of strategy parameters and reports
results sorted by a target metric.

Example:
    sweep = ParameterSweep(
        strategy_class=HRPStrategy,
        param_grid={'linkage_method': ['single', 'complete', 'ward']},
        metric='sharpe_ratio'
    )
    results_df = sweep.run(underlying_assets, prices, start_date, end_date)
"""

import itertools
import logging
from dataclasses import dataclass
from typing import Dict, List, Any, Type

import pandas as pd
import numpy as np

from strategies.core import AllocationStrategy, Strategy, StrategyContext
from analytics.metrics import (
    calculate_returns, calculate_sharpe_ratio, calculate_sortino_ratio,
    calculate_calmar_ratio, calculate_volatility, calculate_max_drawdown,
    calculate_cagr, calculate_var, calculate_cvar
)

logger = logging.getLogger(__name__)


@dataclass
class SweepResult:
    """Result from a single parameter combination."""
    params: Dict[str, Any]
    metrics: Dict[str, float]


class ParameterSweep:
    """
    Grid search across strategy parameter combinations.

    Runs backtests for every combination of parameters in the grid,
    calculates metrics for each, and returns a sorted results table.
    """

    def __init__(
        self,
        strategy_class: Type[AllocationStrategy],
        param_grid: Dict[str, List[Any]],
        metric: str = 'sharpe_ratio',
        initial_capital: float = 10000.0,
        transaction_cost_bps: float = 7.5,
        rebalance_frequency: str = 'monthly'
    ):
        """
        Args:
            strategy_class: Strategy class to optimize
            param_grid: Dict mapping parameter names to lists of values to try
            metric: Target metric to optimize (default: 'sharpe_ratio')
            initial_capital: Starting capital for backtests
            transaction_cost_bps: Transaction cost in basis points
            rebalance_frequency: Rebalancing frequency
        """
        self.strategy_class = strategy_class
        self.param_grid = param_grid
        self.metric = metric
        self.initial_capital = initial_capital
        self.transaction_cost_bps = transaction_cost_bps
        self.rebalance_frequency = rebalance_frequency

    def _generate_combinations(self) -> List[Dict[str, Any]]:
        """Generate all parameter combinations from grid."""
        keys = list(self.param_grid.keys())
        values = list(self.param_grid.values())
        return [dict(zip(keys, combo)) for combo in itertools.product(*values)]

    def _calculate_all_metrics(self, values: pd.Series) -> Dict[str, float]:
        """Calculate all metrics for a portfolio value series."""
        returns = calculate_returns(values).dropna()
        cagr = calculate_cagr(values)
        max_dd = calculate_max_drawdown(values)

        return {
            'total_return': (values.iloc[-1] / values.iloc[0] - 1) * 100,
            'cagr': cagr * 100,
            'sharpe_ratio': calculate_sharpe_ratio(returns),
            'sortino_ratio': calculate_sortino_ratio(returns),
            'calmar_ratio': cagr / abs(max_dd) if max_dd != 0 else 0,
            'max_drawdown': max_dd * 100,
            'volatility': calculate_volatility(returns) * 100,
            'var_95': calculate_var(returns) * 100,
            'cvar_95': calculate_cvar(returns) * 100,
        }

    def run(
        self,
        underlying: List[Strategy],
        prices: pd.DataFrame,
        start_date,
        end_date,
        lookback_days: int = 252
    ) -> pd.DataFrame:
        """
        Run parameter sweep.

        Args:
            underlying: List of underlying asset strategies
            prices: Historical price DataFrame (columns=symbols, index=dates)
            start_date: Backtest start date
            end_date: Backtest end date
            lookback_days: Days before start_date needed for strategy lookback

        Returns:
            DataFrame with one row per parameter combination,
            columns = param names + metric names, sorted by target metric
        """
        from backtesting.portfolio_state import PortfolioState

        combinations = self._generate_combinations()
        logger.info(f"Running {len(combinations)} parameter combinations")

        # Filter prices to relevant date range
        backtest_prices = prices[
            (prices.index >= start_date) & (prices.index <= end_date)
        ]

        # Generate rebalance dates
        freq_map = {'monthly': 'ME', 'weekly': 'W', 'quarterly': 'QE', 'daily': 'D'}
        freq = freq_map.get(self.rebalance_frequency, 'ME')
        candidate_dates = pd.date_range(start=start_date, end=end_date, freq=freq)
        rebalance_dates = []
        for date in candidate_dates:
            future = backtest_prices.index[backtest_prices.index >= date]
            if len(future) > 0:
                rebalance_dates.append(future[0])

        results = []

        for i, params in enumerate(combinations):
            try:
                # Create strategy with these params
                strategy = self.strategy_class(underlying=underlying, **params)

                # Get strategy's actual lookback
                actual_lookback = strategy.get_strategy_lookback()
                total_lookback = max(lookback_days, actual_lookback)
                if hasattr(strategy, 'smooth_window'):
                    total_lookback += strategy.smooth_window

                # Run simplified backtest
                portfolio = PortfolioState(
                    timestamp=start_date,
                    cash=self.initial_capital,
                    positions={},
                    prices={}
                )

                history = []

                for rebalance_date in rebalance_dates:
                    # Create context with lookback
                    lookback_start = rebalance_date - pd.Timedelta(days=int(total_lookback * 1.5))
                    context_prices = prices[
                        (prices.index >= lookback_start) &
                        (prices.index <= rebalance_date)
                    ]

                    if len(context_prices) < 30:
                        continue

                    context = StrategyContext(
                        current_date=rebalance_date,
                        lookback_start=context_prices.index[0],
                        prices=context_prices
                    )

                    try:
                        weights = strategy.calculate_weights(context)
                        current_prices = backtest_prices.loc[rebalance_date]

                        portfolio.timestamp = rebalance_date
                        portfolio.execute_rebalance(
                            target_weights=weights,
                            prices=current_prices,
                            transaction_cost_bps=self.transaction_cost_bps
                        )

                        history.append({
                            'timestamp': rebalance_date,
                            'total_value': portfolio.total_value()
                        })
                    except Exception:
                        continue

                if len(history) < 2:
                    logger.warning(f"Combo {i+1}/{len(combinations)} {params}: insufficient data, skipping")
                    continue

                values = pd.Series(
                    [h['total_value'] for h in history],
                    index=pd.to_datetime([h['timestamp'] for h in history])
                )

                metrics = self._calculate_all_metrics(values)

                result_row = {**params, **metrics}
                results.append(result_row)

                logger.info(
                    f"Combo {i+1}/{len(combinations)} {params}: "
                    f"{self.metric}={metrics.get(self.metric, 0):.4f}"
                )

            except Exception as e:
                logger.error(f"Combo {i+1}/{len(combinations)} {params}: failed - {e}")
                continue

        if not results:
            logger.warning("No successful parameter combinations")
            return pd.DataFrame()

        df = pd.DataFrame(results)
        df = df.sort_values(self.metric, ascending=False).reset_index(drop=True)
        return df
