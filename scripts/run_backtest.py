"""
Main script to run portfolio strategy backtests on UK ETFs.

This script:
1. Fetches historical data for all assets defined in strategy_definitions/assets/
2. Runs ALL available strategies in backtests
3. Generates comprehensive results in structured JSON format
4. Outputs data suitable for frontend consumption (strategy picker + comparison mode)

Usage (Run all strategies):
    python run_backtest.py --all                     # Run all available strategies
    python run_backtest.py --all --refresh           # Force fresh data from IB

Usage (Legacy - single strategy vs benchmark):
    python run_backtest.py --strategy hrp --benchmark equal_weight
    python run_backtest.py --strategy trend_following --benchmark hrp_ward
    python run_backtest.py --use-definitions --strategy trend_following
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
import logging
from datetime import datetime

import pandas as pd

# IB Wrapper imports
from ib_wrapper.config import Config

# Strategy imports
from strategies import create_strategy, STRATEGY_REGISTRY, prune_missing_assets
from strategies.strategy_loader import StrategyLoader
from strategies.catalog import extract_strategy_params

# Backtesting imports
from backtesting import BacktestEngine
from backtesting.runner import run_single_backtest
from backtesting.results_io import save_strategy_results, serialize_backtest_results
from backtesting.results_schema import INDEX_FILE

# Analytics imports
from analytics import (
    generate_metrics_summary,
    plot_portfolio_comparison,
    create_performance_table,
)
from analytics.stress_testing import run_stress_test
from analytics.report import write_report

# Data management imports
from data import HistoricalDataCache, align_dataframes, validate_data_quality

# Backtest CLI support package (config, data fetch, batch runner, argparse)
from backtest_lib.cli import parse_args
from backtest_lib.config import (  # noqa: F401 — names used throughout main()
    BAR_SIZE,
    CURRENCY,
    END_DATE,
    EXCHANGE,
    INITIAL_CAPITAL,
    LOOKBACK_DAYS,
    REBALANCE_FREQUENCY,
    RESULTS_DIR,
    SEC_TYPE,
    START_DATE,
    SYMBOLS,
    TRANSACTION_COST_BPS,
)
from backtest_lib.data_fetch import fetch_historical_data
from backtest_lib.run_all import run_all_strategies

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main(args):
    """
    Main execution function.

    Args:
        args: Parsed command-line arguments
    """
    # Check if running all strategies
    if args.all:
        logger.info("Mode: Running ALL available strategies")
        args.use_definitions = True  # Force definitions mode for all strategy run
        primary_strategy = None
        benchmark_strategy = None
        strategy_display = None
        benchmark_display = None
    elif args.use_definitions:
        logger.info("Loading strategies from YAML definitions...")
        loader = StrategyLoader()

        try:
            if args.composed_strategy:
                # Load composed strategy
                primary_strategy = loader.build_composed_strategy(
                    args.composed_strategy
                )
                strategy_display = args.composed_strategy
            else:
                # Load allocation + underlying + overlays
                primary_strategy = loader.build_strategy(args.strategy)
                strategy_display = STRATEGY_REGISTRY.get(args.strategy, {}).get(
                    "display_name", args.strategy
                )

            benchmark_strategy = loader.build_strategy(args.benchmark)
            benchmark_display = STRATEGY_REGISTRY.get(args.benchmark, {}).get(
                "display_name", args.benchmark
            )

            logger.info(f"✓ Loaded strategies from definitions")
        except Exception as e:
            logger.error(f"Failed to load strategies from definitions: {e}")
            raise
    else:
        # Use traditional registry-based approach
        strategy_display = STRATEGY_REGISTRY[args.strategy]["display_name"]
        benchmark_display = STRATEGY_REGISTRY[args.benchmark]["display_name"]

        # Extract strategy-specific parameters
        strategy_params = extract_strategy_params(args, args.strategy)
        benchmark_params = extract_strategy_params(args, args.benchmark)

        logger.info(f"\nInitializing {strategy_display}...")
        if strategy_params:
            logger.info(f"  Parameters: {strategy_params}")
        primary_strategy = create_strategy(args.strategy, **strategy_params)

        logger.info(f"\nInitializing {benchmark_display}...")
        if benchmark_params:
            logger.info(f"  Parameters: {benchmark_params}")
        benchmark_strategy = create_strategy(args.benchmark, **benchmark_params)

    print("\n" + "=" * 60)
    print("PORTFOLIO STRATEGY BACKTEST")
    print("=" * 60)
    if args.all:
        print("Mode: Running ALL available strategies")
    else:
        print(f"Primary Strategy: {strategy_display}")
        print(f"Benchmark: {benchmark_display}")
    print(f"Symbols: {', '.join(SYMBOLS)}")
    print(f"Currency: {CURRENCY}")
    print(f"Initial Capital: £{INITIAL_CAPITAL:,.2f}")
    print(f"Transaction Cost: {TRANSACTION_COST_BPS} basis points")
    print(f"Rebalance Frequency: {REBALANCE_FREQUENCY}")
    print(f"Lookback Period: {LOOKBACK_DAYS} days (1 year)")
    if args.refresh:
        print("Data Mode: FRESH FROM IB (cache skipped)")
    else:
        print("Data Mode: Using cache if available (faster)")
    if args.all:
        print("Strategy Mode: YAML Definitions (All)")
    elif args.use_definitions:
        print("Strategy Mode: YAML Definitions")
    else:
        print("Strategy Mode: Registry-based")
    print("=" * 60 + "\n")

    # Initialize cache
    cache = HistoricalDataCache(cache_dir="data/cache")

    # Fetch data — cache-first, connecting to IB lazily only on a cache miss.
    logger.info("Loading historical data (IB connection opened only if needed)...")

    try:
        config = Config()

        # Fetch historical data (opens an IB socket only for missing symbols)
        data_dict = await fetch_historical_data(config, cache, refresh=args.refresh)

        if not data_dict:
            logger.error("No data fetched. Exiting.")
            return

        # Align data
        logger.info("\n" + "=" * 60)
        logger.info("PREPROCESSING DATA")
        logger.info("=" * 60)

        prices = align_dataframes(data_dict)

        if prices.empty:
            logger.error("Failed to align data. Exiting.")
            return

        # Validate data quality
        if not validate_data_quality(prices, min_data_points=LOOKBACK_DAYS):
            logger.error("Data quality validation failed. Exiting.")
            return

        # Determine actual backtest date range
        # Need LOOKBACK_DAYS before first rebalance
        backtest_start = prices.index[LOOKBACK_DAYS]
        backtest_end = prices.index[-1]

        logger.info(
            f"\nBacktest period: {backtest_start.date()} to {backtest_end.date()}"
        )
        logger.info(f"Backtest days: {len(prices[backtest_start:])} days")

    except Exception as e:
        logger.error(f"Failed to connect to IB or fetch data: {e}")
        logger.info("Attempting to use cached data only...")

        # Try to load from cache
        cache = HistoricalDataCache(cache_dir="data/cache")
        data_dict = {}

        for symbol in SYMBOLS:
            df = cache.load_cached_data(symbol, START_DATE, END_DATE, max_age_days=30)
            if not df.empty:
                data_dict[symbol] = df

        if not data_dict:
            logger.error("No cached data available. Exiting.")
            return

        prices = align_dataframes(data_dict)

        if prices.empty or not validate_data_quality(
            prices, min_data_points=LOOKBACK_DAYS
        ):
            logger.error("Insufficient cached data. Exiting.")
            return

        backtest_start = prices.index[LOOKBACK_DAYS]
        backtest_end = prices.index[-1]

    # Run backtests
    if args.all:
        # Run all available strategies
        all_strategy_results = await run_all_strategies(
            args, prices, backtest_start, backtest_end
        )

        # Save individual results to separate files
        logger.info("\n" + "=" * 60)
        logger.info("SAVING INDIVIDUAL STRATEGY RESULTS")
        logger.info("=" * 60)

        run_config = {
            "symbols": SYMBOLS,
            "currency": CURRENCY,
            "initial_capital": INITIAL_CAPITAL,
            "transaction_cost_bps": TRANSACTION_COST_BPS,
            "rebalance_frequency": REBALANCE_FREQUENCY,
            "lookback_days": LOOKBACK_DAYS,
        }

        # save_strategy_results() always merges into strategies_index.json
        # (see backtesting/results_io.py). Reset it once before this run's
        # per-strategy loop so the index ends up scoped to exactly the
        # strategies produced by this --all run, matching the old inline
        # block's full-rebuild behaviour.
        index_path = RESULTS_DIR / INDEX_FILE
        if index_path.exists():
            index_path.unlink()

        for strategy_key, result_data in all_strategy_results.items():
            stress_report = None
            # Rerun scenario-removal was computed upstream where the live
            # strategy/engine existed; prefer it over the cheap excise path.
            if result_data.get("_stress_report") is not None:
                stress_report = result_data.pop("_stress_report")
            elif args.stress_test:
                try:
                    ph = result_data["portfolio_history"]
                    values_series = pd.Series(
                        {entry["date"]: entry["total_value"] for entry in ph}
                    )
                    values_series.index = pd.to_datetime(values_series.index)
                    values_series = values_series.sort_index()
                    report = run_stress_test(
                        values_series,
                        strategy_name=result_data["info"].get("name", strategy_key),
                    )
                    stress_report = report.to_dict()
                except Exception as exc:
                    logger.warning(f"  ⚠ Stress test failed for {strategy_key}: {exc}")

            save_strategy_results(
                result_data,
                strategy_key,
                RESULTS_DIR,
                stress_report=stress_report,
                config=run_config,
            )

            if args.report:
                try:
                    written = write_report(strategy_key, RESULTS_DIR, fmt="md")
                    logger.info(f"  ✓ Report written: {written['md']}")
                except Exception as exc:
                    logger.warning(
                        f"  ⚠ Report generation failed for {strategy_key}: {exc}"
                    )

        logger.info(f"✓ Strategies index saved to: {index_path}")

        # Print summary
        logger.info("\n" + "=" * 60)
        logger.info("BACKTEST SUMMARY")
        logger.info("=" * 60)
        for strategy_key, result_data in sorted(all_strategy_results.items()):
            metrics = result_data["metrics"]
            logger.info(f"\n{strategy_key}:")
            logger.info(f"  Final Value: £{metrics['final_value']:,.2f}")
            logger.info(f"  Total Return: {metrics['total_return']:.2%}")
            logger.info(f"  Volatility: {metrics['volatility']:.2%}")
            logger.info(f"  Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
            logger.info(f"  Max Drawdown: {metrics['max_drawdown']:.2%}")

    else:
        # Legacy mode: Run single strategy vs benchmark
        logger.info("\n" + "=" * 60)
        logger.info("RUNNING BACKTESTS")
        logger.info("=" * 60)

        # Initialize backtest engine
        engine = BacktestEngine(
            initial_capital=INITIAL_CAPITAL,
            transaction_cost_bps=TRANSACTION_COST_BPS,
            rebalance_frequency=REBALANCE_FREQUENCY,
        )

        # Drop any assets that failed to fetch so strategies rebalance across
        # only the assets with actual price data.
        available_symbols = set(prices.columns)
        primary_strategy = prune_missing_assets(primary_strategy, available_symbols)
        benchmark_strategy = prune_missing_assets(benchmark_strategy, available_symbols)
        if primary_strategy is None:
            logger.error(
                f"{strategy_display}: no assets with price data remain. Exiting."
            )
            return
        if benchmark_strategy is None:
            logger.error(
                f"{benchmark_display}: no assets with price data remain. Exiting."
            )
            return

        # Run primary strategy backtest
        logger.info(f"\nRunning {strategy_display} backtest...")
        primary_results = run_single_backtest(
            primary_strategy,
            prices,
            backtest_start,
            backtest_end,
            engine,
            default_lookback_days=LOOKBACK_DAYS,
        )

        # Generate metrics
        generate_metrics_summary(primary_results)
        logger.info(f"  {strategy_display} backtest complete")
        logger.info(f"  - Rebalances: {len(primary_results.portfolio_history)}")
        logger.info(f"  - Transactions: {len(primary_results.transactions)}")
        logger.info(f"  - Final value: {primary_results.final_value:,.2f}")

        # Run benchmark strategy backtest
        logger.info(f"\nRunning {benchmark_display} backtest...")
        benchmark_results = run_single_backtest(
            benchmark_strategy,
            prices,
            backtest_start,
            backtest_end,
            engine,
            default_lookback_days=LOOKBACK_DAYS,
        )

        # Generate metrics
        generate_metrics_summary(benchmark_results)
        logger.info(f"✓ {benchmark_display} backtest complete")
        logger.info(f"  - Rebalances: {len(benchmark_results.portfolio_history)}")
        logger.info(f"  - Transactions: {len(benchmark_results.transactions)}")
        logger.info(f"  - Final value: £{benchmark_results.final_value:,.2f}")

        # Performance Summary
        logger.info("\n" + "=" * 60)
        logger.info("PERFORMANCE SUMMARY")
        logger.info("=" * 60)

        results_dict = {
            strategy_display: primary_results,
            benchmark_display: benchmark_results,
        }

        # Create performance table
        perf_table = create_performance_table(results_dict)
        print("\n" + str(perf_table))

        # Save results
        logger.info("\n" + "=" * 60)
        logger.info("SAVING RESULTS")
        logger.info("=" * 60)

        # Save portfolio histories (use fixed prefixes for dashboard compatibility)
        primary_history_path = RESULTS_DIR / "hrp_portfolio_history.csv"
        primary_results.portfolio_history.to_csv(primary_history_path)
        logger.info(
            f"✓ {strategy_display} portfolio history saved to: {primary_history_path}"
        )

        benchmark_history_path = RESULTS_DIR / "ew_portfolio_history.csv"
        benchmark_results.portfolio_history.to_csv(benchmark_history_path)
        logger.info(
            f"✓ {benchmark_display} portfolio history saved to: {benchmark_history_path}"
        )

        # Save transactions
        primary_tx_df = pd.DataFrame(
            [
                {
                    "timestamp": t.timestamp,
                    "symbol": t.symbol,
                    "quantity": t.quantity,
                    "price": t.price,
                    "cost": t.total_cost,
                }
                for t in primary_results.transactions
            ]
        )
        primary_tx_path = RESULTS_DIR / "hrp_transactions.csv"
        primary_tx_df.to_csv(primary_tx_path, index=False)
        logger.info(f"✓ {strategy_display} transactions saved to: {primary_tx_path}")

        benchmark_tx_df = pd.DataFrame(
            [
                {
                    "timestamp": t.timestamp,
                    "symbol": t.symbol,
                    "quantity": t.quantity,
                    "price": t.price,
                    "cost": t.total_cost,
                }
                for t in benchmark_results.transactions
            ]
        )
        benchmark_tx_path = RESULTS_DIR / "ew_transactions.csv"
        benchmark_tx_df.to_csv(benchmark_tx_path, index=False)
        logger.info(f"✓ {benchmark_display} transactions saved to: {benchmark_tx_path}")

        # Save performance metrics
        perf_table_path = RESULTS_DIR / "performance_comparison.csv"
        perf_table.to_csv(perf_table_path)
        logger.info(f"✓ Performance table saved to: {perf_table_path}")

        # Save metadata for dashboard
        if args.use_definitions:
            if args.composed_strategy:
                primary_info = {
                    "name": args.composed_strategy,
                    "display_name": strategy_display,
                    "type": "composed",
                    "params": None,
                }
                benchmark_info = None
            else:
                primary_info = {
                    "name": args.strategy,
                    "display_name": strategy_display,
                    "type": "definition",
                    "params": None,
                }
                benchmark_info = {
                    "name": args.benchmark,
                    "display_name": benchmark_display,
                    "type": "definition",
                    "params": None,
                }
        else:
            strategy_params = extract_strategy_params(args, args.strategy)
            benchmark_params = extract_strategy_params(args, args.benchmark)
            primary_info = {
                "name": args.strategy,
                "display_name": strategy_display,
                "type": "registry",
                "params": strategy_params,
            }
            benchmark_info = {
                "name": args.benchmark,
                "display_name": benchmark_display,
                "type": "registry",
                "params": benchmark_params,
            }

        metadata = {
            "primary_strategy": primary_info,
            "benchmark_strategy": benchmark_info,
            "run_date": datetime.now().isoformat(),
            "strategy_mode": "definitions" if args.use_definitions else "registry",
            "config": {
                "symbols": SYMBOLS,
                "currency": CURRENCY,
                "initial_capital": INITIAL_CAPITAL,
                "transaction_cost_bps": TRANSACTION_COST_BPS,
                "rebalance_frequency": REBALANCE_FREQUENCY,
                "lookback_days": LOOKBACK_DAYS,
            },
        }

        metadata_path = RESULTS_DIR / "metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)
        logger.info(f"✓ Metadata saved to: {metadata_path}")

        # Save primary strategy to per-strategy dir and update strategies_index.json
        # so the dashboard picks it up without needing a full --all run.
        if args.use_definitions:
            strategy_key_for_index = args.composed_strategy or args.strategy
            loader = StrategyLoader()
            try:
                definition = loader.load_definition(strategy_key_for_index)
                strategy_info_for_index = {
                    "key": strategy_key_for_index,
                    "type": definition.get("type"),
                    "class": definition.get("class"),
                    "description": definition.get("description", ""),
                    "parameters": definition.get("parameters", {}),
                }
            except Exception:
                strategy_info_for_index = {"key": strategy_key_for_index}
            serialized = serialize_backtest_results(
                primary_results, strategy_key_for_index, strategy_info_for_index
            )
            save_strategy_results(
                serialized,
                strategy_key_for_index,
                RESULTS_DIR,
                config=metadata["config"],
            )

            if args.report:
                try:
                    written = write_report(
                        strategy_key_for_index, RESULTS_DIR, fmt="md"
                    )
                    logger.info(f"✓ Report written: {written['md']}")
                except Exception as exc:
                    logger.warning(f"⚠ Report generation failed: {exc}")

        # Create and save visualization
        logger.info("\nGenerating performance charts...")
        fig = plot_portfolio_comparison(
            results_dict, save_path=str(RESULTS_DIR / "performance_charts.png")
        )
        logger.info(
            f"✓ Performance charts saved to: {RESULTS_DIR / 'performance_charts.png'}"
        )

    logger.info("\n" + "=" * 60)
    logger.info("BACKTEST COMPLETE")
    logger.info("=" * 60)
    logger.info(f"\nResults saved to: {RESULTS_DIR.absolute()}")


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
