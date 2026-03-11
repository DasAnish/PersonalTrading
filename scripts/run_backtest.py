"""
Main script to run portfolio strategy backtests on UK ETFs.

This script:
1. Fetches historical data for UK ETFs (VUSA, SSLN, SGLN, IWRD)
2. Runs specified strategy and benchmark comparison
3. Generates performance metrics and visualizations
4. Saves results to CSV, PNG, and metadata JSON files

Usage:
    python run_backtest.py                           # Default: HRP vs Equal Weight
    python run_backtest.py --refresh                 # Force fresh data from IB
    python run_backtest.py --strategy hrp --hrp-linkage-method ward
    python run_backtest.py --strategy equal_weight --benchmark hrp
"""

import asyncio
import logging
import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

# IB Wrapper imports
from ib_wrapper.client import IBClient
from ib_wrapper.config import Config

# Strategy imports
from strategies import create_strategy, get_available_strategies, STRATEGY_REGISTRY

# Backtesting imports
from backtesting import BacktestEngine

# Analytics imports
from analytics import generate_metrics_summary, plot_portfolio_comparison, create_performance_table

# Data management imports
from data import HistoricalDataCache, align_dataframes, validate_data_quality

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Configuration
SYMBOLS = ['VUSA', 'SSLN', 'SGLN', 'IWRD']
EXCHANGE = 'SMART'
CURRENCY = 'GBP'
SEC_TYPE = 'STK'
INITIAL_CAPITAL = 10000.0  # GBP
TRANSACTION_COST_BPS = 7.5
REBALANCE_FREQUENCY = 'monthly'
LOOKBACK_DAYS = 252  # 1 year for HRP calculation
BAR_SIZE = '1 day'

# Date range - fetch maximum available history
END_DATE = datetime.now()
START_DATE = END_DATE - timedelta(days=365 * 10)  # Try to get 10 years

# Output paths
RESULTS_DIR = Path('results')
RESULTS_DIR.mkdir(exist_ok=True)


async def fetch_historical_data(client: IBClient, cache: HistoricalDataCache, refresh: bool = False):
    """
    Fetch historical data for all symbols.

    Args:
        client: IBClient instance
        cache: HistoricalDataCache instance
        refresh: If True, force fresh data from IB (skip cache). If False, use cache if available.

    Returns:
        Dict mapping symbol to DataFrame
    """
    logger.info("=" * 60)
    if refresh:
        logger.info("FETCHING FRESH DATA FROM INTERACTIVE BROKERS (CACHE SKIPPED)")
    else:
        logger.info("FETCHING HISTORICAL DATA (USING CACHE IF AVAILABLE)")
    logger.info("=" * 60)

    data_dict = {}

    for symbol in SYMBOLS:
        logger.info(f"\nFetching {symbol}...")

        try:
            if refresh:
                # Force fresh fetch from IB, skip cache
                logger.info(f"  (fetching fresh from IB...)")
                df = await client.market_data.download_extended_history(
                    symbol=symbol,
                    start_date=START_DATE,
                    end_date=END_DATE,
                    bar_size=BAR_SIZE,
                    sec_type=SEC_TYPE,
                    exchange=EXCHANGE,
                    currency=CURRENCY
                )
                # Save to cache for future use
                if not df.empty:
                    cache.save_cached_data(symbol, df, START_DATE, END_DATE)
            else:
                # Use cache-aware fetch (faster, uses existing data if available)
                df = await cache.get_or_fetch_data(
                    symbol=symbol,
                    start_date=START_DATE,
                    end_date=END_DATE,
                    market_data_service=client.market_data,
                    bar_size=BAR_SIZE,
                    sec_type=SEC_TYPE,
                    exchange=EXCHANGE,
                    currency=CURRENCY
                )

            if not df.empty:
                data_dict[symbol] = df
                logger.info(
                    f"✓ {symbol}: {len(df)} days "
                    f"({df.index[0].date()} to {df.index[-1].date()})"
                )
            else:
                logger.warning(f"✗ {symbol}: No data received")

        except Exception as e:
            logger.error(f"✗ {symbol}: Failed to fetch - {e}")

    return data_dict


def extract_strategy_params(args, strategy_name: str) -> dict:
    """
    Extract parameters for a specific strategy from CLI args.

    Args:
        args: Parsed command-line arguments
        strategy_name: Strategy key (e.g., 'hrp')

    Returns:
        Dictionary of strategy-specific parameters
    """
    config = STRATEGY_REGISTRY[strategy_name]
    params = {}

    for param_name in config.get('params', {}).keys():
        arg_name = f'{strategy_name}_{param_name}'
        if hasattr(args, arg_name):
            value = getattr(args, arg_name)
            if value is not None:
                params[param_name] = value

    return params


async def main(args):
    """
    Main execution function.

    Args:
        args: Parsed command-line arguments
    """
    # Get strategy display names
    strategy_display = STRATEGY_REGISTRY[args.strategy]['display_name']
    benchmark_display = STRATEGY_REGISTRY[args.benchmark]['display_name']

    print("\n" + "=" * 60)
    print("PORTFOLIO STRATEGY BACKTEST")
    print("=" * 60)
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
    print("=" * 60 + "\n")

    # Initialize cache
    cache = HistoricalDataCache(cache_dir='data/cache')

    # Connect to IB
    logger.info("Connecting to Interactive Brokers...")

    try:
        config = Config()
        async with IBClient(config) as client:
            logger.info("✓ Connected to IB")

            # Fetch historical data
            data_dict = await fetch_historical_data(client, cache, refresh=args.refresh)

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
        cache = HistoricalDataCache(cache_dir='data/cache')
        data_dict = {}

        for symbol in SYMBOLS:
            df = cache.load_cached_data(symbol, START_DATE, END_DATE, max_age_days=30)
            if not df.empty:
                data_dict[symbol] = df

        if not data_dict:
            logger.error("No cached data available. Exiting.")
            return

        prices = align_dataframes(data_dict)

        if prices.empty or not validate_data_quality(prices, min_data_points=LOOKBACK_DAYS):
            logger.error("Insufficient cached data. Exiting.")
            return

        backtest_start = prices.index[LOOKBACK_DAYS]
        backtest_end = prices.index[-1]

    # Initialize strategies
    logger.info("\n" + "=" * 60)
    logger.info("RUNNING BACKTESTS")
    logger.info("=" * 60)

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

    # Initialize backtest engine
    engine = BacktestEngine(
        initial_capital=INITIAL_CAPITAL,
        transaction_cost_bps=TRANSACTION_COST_BPS,
        rebalance_frequency=REBALANCE_FREQUENCY,
        lookback_days=LOOKBACK_DAYS
    )

    # Run primary strategy backtest
    logger.info(f"\nRunning {strategy_display} backtest...")
    primary_results = engine.run_backtest(
        strategy=primary_strategy,
        historical_data=prices,
        start_date=backtest_start,
        end_date=backtest_end
    )

    # Generate metrics
    generate_metrics_summary(primary_results)
    logger.info(f"✓ {strategy_display} backtest complete")
    logger.info(f"  - Rebalances: {len(primary_results.portfolio_history)}")
    logger.info(f"  - Transactions: {len(primary_results.transactions)}")
    logger.info(f"  - Final value: £{primary_results.final_value:,.2f}")

    # Run benchmark strategy backtest
    logger.info(f"\nRunning {benchmark_display} backtest...")
    benchmark_results = engine.run_backtest(
        strategy=benchmark_strategy,
        historical_data=prices,
        start_date=backtest_start,
        end_date=backtest_end
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
        benchmark_display: benchmark_results
    }

    # Create performance table
    perf_table = create_performance_table(results_dict)
    print("\n" + str(perf_table))

    # Save results
    logger.info("\n" + "=" * 60)
    logger.info("SAVING RESULTS")
    logger.info("=" * 60)

    # Save portfolio histories (use fixed prefixes for dashboard compatibility)
    primary_history_path = RESULTS_DIR / 'hrp_portfolio_history.csv'
    primary_results.portfolio_history.to_csv(primary_history_path)
    logger.info(f"✓ {strategy_display} portfolio history saved to: {primary_history_path}")

    benchmark_history_path = RESULTS_DIR / 'ew_portfolio_history.csv'
    benchmark_results.portfolio_history.to_csv(benchmark_history_path)
    logger.info(f"✓ {benchmark_display} portfolio history saved to: {benchmark_history_path}")

    # Save transactions
    import pandas as pd

    primary_tx_df = pd.DataFrame([
        {
            'timestamp': t.timestamp,
            'symbol': t.symbol,
            'quantity': t.quantity,
            'price': t.price,
            'cost': t.total_cost
        }
        for t in primary_results.transactions
    ])
    primary_tx_path = RESULTS_DIR / 'hrp_transactions.csv'
    primary_tx_df.to_csv(primary_tx_path, index=False)
    logger.info(f"✓ {strategy_display} transactions saved to: {primary_tx_path}")

    benchmark_tx_df = pd.DataFrame([
        {
            'timestamp': t.timestamp,
            'symbol': t.symbol,
            'quantity': t.quantity,
            'price': t.price,
            'cost': t.total_cost
        }
        for t in benchmark_results.transactions
    ])
    benchmark_tx_path = RESULTS_DIR / 'ew_transactions.csv'
    benchmark_tx_df.to_csv(benchmark_tx_path, index=False)
    logger.info(f"✓ {benchmark_display} transactions saved to: {benchmark_tx_path}")

    # Save performance metrics
    perf_table_path = RESULTS_DIR / 'performance_comparison.csv'
    perf_table.to_csv(perf_table_path)
    logger.info(f"✓ Performance table saved to: {perf_table_path}")

    # Save metadata for dashboard
    metadata = {
        'primary_strategy': {
            'name': args.strategy,
            'display_name': strategy_display,
            'params': strategy_params
        },
        'benchmark_strategy': {
            'name': args.benchmark,
            'display_name': benchmark_display,
            'params': benchmark_params
        },
        'run_date': datetime.now().isoformat(),
        'config': {
            'symbols': SYMBOLS,
            'currency': CURRENCY,
            'initial_capital': INITIAL_CAPITAL,
            'transaction_cost_bps': TRANSACTION_COST_BPS,
            'rebalance_frequency': REBALANCE_FREQUENCY,
            'lookback_days': LOOKBACK_DAYS
        }
    }

    metadata_path = RESULTS_DIR / 'metadata.json'
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    logger.info(f"✓ Metadata saved to: {metadata_path}")

    # Create and save visualization
    logger.info("\nGenerating performance charts...")
    fig = plot_portfolio_comparison(
        results_dict,
        save_path=str(RESULTS_DIR / 'performance_charts.png')
    )
    logger.info(f"✓ Performance charts saved to: {RESULTS_DIR / 'performance_charts.png'}")

    logger.info("\n" + "=" * 60)
    logger.info("BACKTEST COMPLETE")
    logger.info("=" * 60)
    logger.info(f"\nResults saved to: {RESULTS_DIR.absolute()}")


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Run portfolio strategy backtest on UK ETFs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_backtest.py                                    # Default: HRP vs Equal Weight
  python run_backtest.py --refresh                          # Force fresh data from IB
  python run_backtest.py --strategy hrp --hrp-linkage-method ward
  python run_backtest.py --strategy equal_weight --benchmark hrp
        """
    )

    # Strategy selection
    parser.add_argument(
        '--strategy',
        type=str,
        default='hrp',
        choices=get_available_strategies(),
        help='Primary strategy to test (default: hrp)'
    )

    parser.add_argument(
        '--benchmark',
        type=str,
        default='equal_weight',
        choices=get_available_strategies(),
        help='Benchmark strategy for comparison (default: equal_weight)'
    )

    # Data refresh flag
    parser.add_argument(
        '--refresh',
        action='store_true',
        help='Force fresh data from Interactive Brokers (skip cache). '
             'Useful for getting the latest market data.'
    )

    # Strategy-specific parameters (dynamically generated)
    for strategy_key, config in STRATEGY_REGISTRY.items():
        for param_name, param_config in config.get('params', {}).items():
            arg_name = f'--{strategy_key}-{param_name.replace("_", "-")}'
            parser.add_argument(
                arg_name,
                type=param_config['type'],
                default=param_config.get('default'),
                choices=param_config.get('choices'),
                help=param_config.get('help', f'{param_name} for {strategy_key}')
            )

    args = parser.parse_args()

    # Validation
    if args.strategy == args.benchmark:
        parser.error("Strategy and benchmark must be different")

    # Run the async main function
    asyncio.run(main(args))
