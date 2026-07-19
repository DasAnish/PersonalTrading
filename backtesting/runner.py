"""
Programmatic backtest runner.

Runs a single ``Strategy`` (asset, allocation, overlay, or composed) directly
against a pre-fetched, aligned price ``DataFrame`` — bypassing the
``MarketDataService``/IB Gateway data path entirely. This is the core
simulation loop shared by ``scripts/run_backtest.py`` (both ``--all`` and
legacy single-strategy modes) and, going forward, any programmatic caller
(report exporters, CPCV/bootstrap/scenario-rerun tooling).

Moved from ``scripts/run_backtest.py`` (Phase 3 refactor):
    ``_run_single_backtest``      -> ``run_single_backtest``
    ``_compute_portfolio_values`` -> ``compute_portfolio_values``

The former module-global ``LOOKBACK_DAYS`` dependency is replaced by an
explicit ``default_lookback_days`` parameter (default ``252``, matching the
prior global default) so this module has no dependency on the CLI script.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from strategies.core import OverlayStrategy, Strategy, StrategyContext

from .engine import BacktestEngine, BacktestResults
from .portfolio_state import PortfolioState

logger = logging.getLogger(__name__)


def compute_portfolio_values(
    strategy: Strategy,
    prices: pd.DataFrame,
    backtest_start: datetime,
    backtest_end: datetime,
    engine: BacktestEngine,
    default_lookback_days: int = 252,
) -> pd.Series:
    """Run a strategy and return its portfolio-value time-series.

    Used by overlay strategies that need the underlying portfolio's history
    (e.g. VolatilityTargetStrategy computes realised vol from these values).

    Args:
        strategy: Any Strategy instance (typically the overlay's underlying)
        prices: Aligned price DataFrame (columns=symbols, index=dates)
        backtest_start: First rebalance date
        backtest_end: Last rebalance date
        engine: BacktestEngine (for rebalance dates and transaction cost)
        default_lookback_days: Fallback lookback (trading days) used when a
            strategy does not declare its own lookback requirement.

    Returns:
        pd.Series of total_value indexed by rebalance date (empty if the
        underlying backtest produced no portfolio history).
    """
    results = run_single_backtest(
        strategy,
        prices,
        backtest_start,
        backtest_end,
        engine,
        default_lookback_days=default_lookback_days,
    )
    if results.portfolio_history.empty:
        return pd.Series(dtype=float)
    return results.portfolio_history["total_value"]


def run_single_backtest(
    strategy: Strategy,
    prices: pd.DataFrame,
    backtest_start: datetime,
    backtest_end: datetime,
    engine: BacktestEngine,
    default_lookback_days: int = 252,
) -> BacktestResults:
    """Run a strategy backtest directly from a pre-fetched prices DataFrame.

    Bypasses MarketDataService so no live IB connection is required after the
    data fetch. Works for allocation, overlay, and composed (stacked overlay)
    strategies.

    Args:
        strategy: Any Strategy instance
        prices: Aligned price DataFrame (columns=symbols, index=dates)
        backtest_start: First rebalance date
        backtest_end: Last rebalance date
        engine: BacktestEngine (for rebalance dates and transaction cost)
        default_lookback_days: Fallback lookback (trading days) used when a
            strategy's ``get_data_requirements()`` does not specify one (or
            raises). Matches the historical module-global ``LOOKBACK_DAYS``
            default of 252 (1 year).

    Returns:
        BacktestResults
    """
    # Determine how much lookback history the strategy needs
    try:
        requirements = strategy.get_data_requirements()
        lookback_days = requirements.lookback_days or default_lookback_days
    except Exception:
        lookback_days = default_lookback_days

    # For overlay strategies, pre-compute the underlying portfolio value series
    portfolio_values: Optional[pd.Series] = None
    if isinstance(strategy, OverlayStrategy):
        portfolio_values = compute_portfolio_values(
            strategy.underlying,
            prices,
            backtest_start,
            backtest_end,
            engine,
            default_lookback_days=default_lookback_days,
        )

    # Generate rebalance dates aligned to actual trading days
    rebalance_dates = engine._generate_rebalance_dates(
        backtest_start, backtest_end, prices.index
    )

    # Initialise portfolio
    portfolio = PortfolioState(
        timestamp=backtest_start, cash=engine.initial_capital, positions={}, prices={}
    )

    portfolio_history = []
    weights_history = []
    all_transactions = []
    failed_rebalances = []

    # Record initial state
    if backtest_start in prices.index:
        portfolio_history.append(
            engine._record_state(portfolio, prices.loc[backtest_start])
        )

    for rebalance_date in rebalance_dates:
        # Convert trading-day lookback to calendar days (+14-day buffer),
        # with a minimum of 60 calendar days so strategies with minimal
        # lookback (e.g. equal_weight with lookback_days=1) always get
        # enough rows to pass the len(sliced) < 5 guard.
        calendar_lookback = max(60, int(lookback_days * 365 / 252) + 14)
        lookback_start = rebalance_date - timedelta(days=calendar_lookback)
        sliced = prices[
            (prices.index >= lookback_start) & (prices.index <= rebalance_date)
        ]

        # Filter to only the symbols this strategy cares about
        try:
            strategy_symbols = strategy.get_symbols()
            available = [s for s in strategy_symbols if s in sliced.columns]
            if available:
                sliced = sliced[available]
        except Exception:
            pass  # fall back to full price frame if get_symbols() fails

        if sliced.empty or len(sliced) < 5:
            continue

        # Pass accumulated portfolio values to overlays (up to current date)
        pv_slice = None
        if portfolio_values is not None and not portfolio_values.empty:
            pv_slice = portfolio_values[portfolio_values.index <= rebalance_date]

        context = StrategyContext(
            current_date=rebalance_date,
            lookback_start=lookback_start,
            prices=sliced,
            portfolio_values=pv_slice,
            metadata={},
        )

        try:
            weights = strategy.calculate_weights(context)
        except (ValueError, KeyError, np.linalg.LinAlgError) as e:
            logger.error(
                f"{strategy.name} failed at rebalance date "
                f"{rebalance_date.date()}: {e}",
                exc_info=True,
            )
            failed_rebalances.append(rebalance_date)
            continue

        weight_record = {"timestamp": rebalance_date}
        weight_record.update(weights.to_dict())
        weights_history.append(weight_record)

        current_prices = prices.loc[rebalance_date]
        portfolio.timestamp = rebalance_date

        transactions = portfolio.execute_rebalance(
            target_weights=weights,
            prices=current_prices,
            transaction_cost_bps=engine.transaction_cost_bps,
        )
        all_transactions.extend(transactions)
        portfolio_history.append(engine._record_state(portfolio, current_prices))

    # Mark-to-market at the latest available price date, even if it falls
    # between rebalances (e.g. mid-month). Repricing only — no trades — so
    # performance/data_end reflect the freshest cached prices instead of
    # freezing at the last completed rebalance.
    if portfolio_history and backtest_end in prices.index:
        last_data_date = backtest_end
        if last_data_date > portfolio_history[-1]["timestamp"]:
            final_prices = prices.loc[last_data_date]
            portfolio.timestamp = last_data_date
            portfolio.prices = final_prices.to_dict()
            portfolio_history.append(engine._record_state(portfolio, final_prices))

    # Assemble result DataFrames
    history_df = pd.DataFrame(portfolio_history)
    if not history_df.empty:
        history_df.set_index("timestamp", inplace=True)

    if weights_history:
        weights_df = pd.DataFrame(weights_history)
        weights_df.set_index("timestamp", inplace=True)
    else:
        weights_df = pd.DataFrame()

    return BacktestResults(
        strategy_name=strategy.name,
        portfolio_history=history_df,
        weights_history=weights_df,
        transactions=all_transactions,
        initial_capital=engine.initial_capital,
        final_value=portfolio.total_value(),
        failed_rebalances=failed_rebalances,
    )
