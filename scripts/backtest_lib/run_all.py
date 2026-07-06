"""Batch runner: execute every available strategy definition in one pass."""

import logging

from strategies import prune_missing_assets
from strategies.catalog import get_all_available_strategies
from backtesting import BacktestEngine
from backtesting.runner import run_single_backtest
from backtesting.results_io import serialize_backtest_results
from analytics.stress_testing import StressTestReport, StressTester

from .config import (
    INITIAL_CAPITAL,
    LOOKBACK_DAYS,
    REBALANCE_FREQUENCY,
    TRANSACTION_COST_BPS,
)

logger = logging.getLogger(__name__)


async def run_all_strategies(args, prices, backtest_start, backtest_end):
    """
    Run all available strategies and generate comprehensive results.

    Args:
        args: Parsed command-line arguments
        prices: Aligned price DataFrame
        backtest_start: Start date for backtest
        backtest_end: End date for backtest

    Returns:
        Dictionary with all strategy results
    """
    logger.info("\n" + "=" * 60)
    logger.info("RUNNING ALL AVAILABLE STRATEGIES")
    logger.info("=" * 60)

    # Get all available strategies
    available_strategies = get_all_available_strategies(use_definitions=True)
    logger.info(f"Found {len(available_strategies)} available strategies")

    # Initialize backtest engine (lookback_days handled per-strategy in run_single_backtest)
    engine = BacktestEngine(
        initial_capital=INITIAL_CAPITAL,
        transaction_cost_bps=TRANSACTION_COST_BPS,
        rebalance_frequency=REBALANCE_FREQUENCY,
    )

    available_symbols = set(prices.columns)
    all_results = {}

    for strategy_key, (strategy, strategy_info) in available_strategies.items():
        try:
            strategy = prune_missing_assets(strategy, available_symbols)
            if strategy is None:
                logger.warning(
                    f"Skipping {strategy_key}: no assets with price data remain"
                )
                continue

            logger.info(f"\nRunning {strategy_key}...")

            results = run_single_backtest(
                strategy,
                prices,
                backtest_start,
                backtest_end,
                engine,
                default_lookback_days=LOOKBACK_DAYS,
            )

            serialized = serialize_backtest_results(
                results, strategy_key, strategy_info
            )
            all_results[strategy_key] = serialized

            # Rerun-mode leave-one-crisis-out: needs the live strategy/engine/
            # prices, which only exist here (the save loop sees serialized
            # dicts only). Stash the full stress report for the save loop.
            if getattr(args, "scenario_removal", False):
                try:
                    values = results.portfolio_history["total_value"]
                    name = strategy_info.get("name", strategy_key)
                    tester = StressTester(values, name)
                    crisis_metrics = [tester._analyse_crisis(c) for c in tester.crises]
                    scenario = tester.run_leave_one_out(
                        mode="rerun",
                        strategy=strategy,
                        prices=prices,
                        engine=engine,
                        backtest_start=backtest_start,
                        backtest_end=backtest_end,
                        default_lookback_days=LOOKBACK_DAYS,
                    )
                    report = StressTestReport(
                        strategy_name=name,
                        crisis_metrics=crisis_metrics,
                        scenario_removal=scenario,
                        scenario_removal_mode="rerun",
                    )
                    serialized["_stress_report"] = report.to_dict()
                except Exception as exc:
                    logger.warning(
                        f"  ⚠ Scenario-removal rerun failed for "
                        f"{strategy_key}: {exc}"
                    )

            logger.info(f"  Final value: £{results.final_value:,.2f}")
            logger.info(f"  Rebalances: {len(results.portfolio_history)}")
            logger.info(f"  Transactions: {len(results.transactions)}")

        except Exception as e:
            logger.error(f"  Failed to run {strategy_key}: {e}")
            import traceback

            traceback.print_exc()
            continue

    return all_results
