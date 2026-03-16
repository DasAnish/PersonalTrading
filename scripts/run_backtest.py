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
from strategies.strategy_loader import StrategyLoader

# Backtesting imports
from backtesting import BacktestEngine, BacktestResults, PortfolioState

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
_ASSETS_DIR = Path(__file__).parent.parent / 'strategy_definitions' / 'assets'
SYMBOLS = sorted(
    json.loads(p.read_text())['parameters']['symbol']
    for p in _ASSETS_DIR.glob('*.json')
)
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


def get_all_available_strategies(use_definitions: bool = True) -> dict:
    """
    Get all available strategies from strategy definitions.

    Args:
        use_definitions: If True, load from YAML definitions; else from registry

    Returns:
        Dict mapping strategy_key to (strategy_object, strategy_info)
    """
    import pandas as pd

    if use_definitions:
        loader = StrategyLoader()
        available = {}

        # Get all allocations, composed strategies, and meta-portfolios
        allocations = loader.list_strategies('allocation')
        composed = loader.list_strategies('composed')
        portfolios = loader.list_strategies('portfolio')

        for strategy_key in list(allocations.keys()) + list(composed.keys()) + list(portfolios.keys()):
            try:
                strategy = loader.build_strategy(strategy_key)
                definition = loader.load_definition(strategy_key)
                info = {
                    'key': strategy_key,
                    'type': definition.get('type'),
                    'class': definition.get('class'),
                    'description': definition.get('description', ''),
                    'parameters': definition.get('parameters', {}),
                }
                available[strategy_key] = (strategy, info)
            except Exception as e:
                logger.warning(f"Could not load strategy {strategy_key}: {e}")

        return available
    else:
        # Use registry
        available = {}
        for strategy_key, config in STRATEGY_REGISTRY.items():
            if strategy_key not in ['hrp', 'equal_weight', 'trend_following']:
                continue  # Only include main allocation strategies
            try:
                strategy = create_strategy(strategy_key)
                info = {
                    'key': strategy_key,
                    'type': 'allocation',
                    'class': config['display_name'],
                    'description': '',
                    'parameters': {},
                }
                available[strategy_key] = (strategy, info)
            except Exception as e:
                logger.warning(f"Could not create strategy {strategy_key}: {e}")

        return available


def serialize_backtest_results(results, strategy_key: str, strategy_info: dict) -> dict:
    """
    Serialize backtest results to JSON-compatible format.

    Args:
        results: BacktestResults object
        strategy_key: Strategy identifier
        strategy_info: Strategy metadata

    Returns:
        Dictionary with all results data
    """
    import pandas as pd
    import numpy as np

    def clean_value(val):
        """Convert NaN/inf to None for JSON serialization."""
        if isinstance(val, float):
            if np.isnan(val) or np.isinf(val):
                return None
            return float(val)
        return val

    # Convert portfolio history to list of dicts
    portfolio_history = []
    if hasattr(results.portfolio_history, 'to_dict'):
        for idx, row in results.portfolio_history.iterrows():
            entry = row.to_dict() if hasattr(row, 'to_dict') else dict(row)
            entry['date'] = idx.isoformat() if hasattr(idx, 'isoformat') else str(idx)
            # Clean NaN values
            entry = {k: clean_value(v) for k, v in entry.items()}
            portfolio_history.append(entry)

    # Convert transactions to list of dicts
    transactions = []
    for t in results.transactions:
        transactions.append({
            'date': t.timestamp.isoformat() if hasattr(t.timestamp, 'isoformat') else str(t.timestamp),
            'symbol': t.symbol,
            'quantity': float(t.quantity),
            'price': float(t.price),
            'cost': float(t.total_cost)
        })

    # Extract weights history if available
    weights_history = []
    if hasattr(results, 'weights_history') and results.weights_history is not None:
        for idx, row in results.weights_history.iterrows():
            entry = row.to_dict() if hasattr(row, 'to_dict') else dict(row)
            entry['date'] = idx.isoformat() if hasattr(idx, 'isoformat') else str(idx)
            # Clean NaN values
            entry = {k: clean_value(v) for k, v in entry.items()}
            weights_history.append(entry)

    # Calculate metrics
    portfolio_values = results.portfolio_history['total_value'].values
    returns = np.diff(portfolio_values) / portfolio_values[:-1]

    total_return = (portfolio_values[-1] - portfolio_values[0]) / portfolio_values[0]
    volatility = np.std(returns) * np.sqrt(252) if len(returns) > 0 else 0
    sharpe_ratio = (np.mean(returns) * 252) / volatility if volatility > 0 else 0

    cumulative = (1 + returns).cumprod()
    running_max = np.maximum.accumulate(cumulative)
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = np.min(drawdown) if len(drawdown) > 0 else 0

    return {
        'key': strategy_key,
        'info': strategy_info,
        'metrics': {
            'total_return': clean_value(float(total_return)),
            'volatility': clean_value(float(volatility)),
            'sharpe_ratio': clean_value(float(sharpe_ratio)),
            'max_drawdown': clean_value(float(max_drawdown)),
            'final_value': clean_value(float(results.final_value)),
            'total_transactions': len(results.transactions),
            'rebalances': len(results.portfolio_history),
        },
        'portfolio_history': portfolio_history,
        'transactions': transactions,
        'weights_history': weights_history,
    }


def _compute_portfolio_values(strategy, prices, backtest_start, backtest_end, engine):
    """Run a strategy and return its portfolio-value time-series.

    Used by overlay strategies that need the underlying portfolio's history
    (e.g. VolatilityTargetStrategy computes realised vol from these values).
    """
    import pandas as pd
    results = _run_single_backtest(strategy, prices, backtest_start, backtest_end, engine)
    if results.portfolio_history.empty:
        return pd.Series(dtype=float)
    return results.portfolio_history['total_value']


def _run_single_backtest(strategy, prices, backtest_start, backtest_end, engine):
    """Run a strategy backtest directly from a pre-fetched prices DataFrame.

    Bypasses MarketDataService so no live IB connection is required after the
    data fetch.  Works for allocation, overlay, and composed (stacked overlay)
    strategies.

    Args:
        strategy      : Any Strategy instance
        prices        : Aligned price DataFrame (columns=symbols, index=dates)
        backtest_start: First rebalance date
        backtest_end  : Last rebalance date
        engine        : BacktestEngine (for rebalance dates and transaction cost)

    Returns:
        BacktestResults
    """
    import pandas as pd
    from datetime import timedelta
    from strategies.core import StrategyContext, OverlayStrategy

    # Determine how much lookback history the strategy needs
    try:
        requirements = strategy.get_data_requirements()
        lookback_days = requirements.lookback_days or LOOKBACK_DAYS
    except Exception:
        lookback_days = LOOKBACK_DAYS

    # For overlay strategies, pre-compute the underlying portfolio value series
    portfolio_values = None
    if isinstance(strategy, OverlayStrategy):
        portfolio_values = _compute_portfolio_values(
            strategy.underlying, prices, backtest_start, backtest_end, engine
        )

    # Generate rebalance dates aligned to actual trading days
    rebalance_dates = engine._generate_rebalance_dates(
        backtest_start, backtest_end, prices.index
    )

    # Initialise portfolio
    portfolio = PortfolioState(
        timestamp=backtest_start,
        cash=engine.initial_capital,
        positions={},
        prices={}
    )

    portfolio_history = []
    weights_history = []
    all_transactions = []

    # Record initial state
    if backtest_start in prices.index:
        portfolio_history.append(engine._record_state(portfolio, prices.loc[backtest_start]))

    for rebalance_date in rebalance_dates:
        # Convert trading-day lookback to calendar days (+14-day buffer),
        # with a minimum of 60 calendar days so strategies with minimal
        # lookback (e.g. equal_weight with lookback_days=1) always get
        # enough rows to pass the len(sliced) < 5 guard.
        calendar_lookback = max(60, int(lookback_days * 365 / 252) + 14)
        lookback_start = rebalance_date - timedelta(days=calendar_lookback)
        sliced = prices[
            (prices.index >= lookback_start) &
            (prices.index <= rebalance_date)
        ]

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
            metadata={}
        )

        try:
            weights = strategy.calculate_weights(context)
        except Exception as e:
            logger.warning(f"{strategy.name} at {rebalance_date.date()}: {e}")
            continue

        weight_record = {'timestamp': rebalance_date}
        weight_record.update(weights.to_dict())
        weights_history.append(weight_record)

        current_prices = prices.loc[rebalance_date]
        portfolio.timestamp = rebalance_date

        transactions = portfolio.execute_rebalance(
            target_weights=weights,
            prices=current_prices,
            transaction_cost_bps=engine.transaction_cost_bps
        )
        all_transactions.extend(transactions)
        portfolio_history.append(engine._record_state(portfolio, current_prices))

    # Assemble result DataFrames
    history_df = pd.DataFrame(portfolio_history)
    if not history_df.empty:
        history_df.set_index('timestamp', inplace=True)

    if weights_history:
        weights_df = pd.DataFrame(weights_history)
        weights_df.set_index('timestamp', inplace=True)
    else:
        weights_df = pd.DataFrame()

    return BacktestResults(
        strategy_name=strategy.name,
        portfolio_history=history_df,
        weights_history=weights_df,
        transactions=all_transactions,
        initial_capital=engine.initial_capital,
        final_value=portfolio.total_value()
    )


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

    # Initialize backtest engine (lookback_days handled per-strategy in _run_single_backtest)
    engine = BacktestEngine(
        initial_capital=INITIAL_CAPITAL,
        transaction_cost_bps=TRANSACTION_COST_BPS,
        rebalance_frequency=REBALANCE_FREQUENCY,
    )

    all_results = {}

    for strategy_key, (strategy, strategy_info) in available_strategies.items():
        try:
            logger.info(f"\nRunning {strategy_key}...")

            results = _run_single_backtest(
                strategy, prices, backtest_start, backtest_end, engine
            )

            serialized = serialize_backtest_results(results, strategy_key, strategy_info)
            all_results[strategy_key] = serialized

            logger.info(f"  Final value: £{results.final_value:,.2f}")
            logger.info(f"  Rebalances: {len(results.portfolio_history)}")
            logger.info(f"  Transactions: {len(results.transactions)}")

        except Exception as e:
            logger.error(f"  Failed to run {strategy_key}: {e}")
            import traceback
            traceback.print_exc()
            continue

    return all_results


def _run_strategy(engine, strategy, prices, backtest_start, backtest_end):
    """
    Run a single strategy, handling both allocation and overlay types.

    For overlay/composed strategies, this runs the underlying allocation first,
    then applies overlay transformations via run_backtest_with_overlay.

    Args:
        engine: BacktestEngine instance
        strategy: Strategy to run (AllocationStrategy or OverlayStrategy)
        prices: Aligned price DataFrame
        backtest_start: Start date
        backtest_end: End date

    Returns:
        BacktestResults
    """
    from strategies.base import OverlayStrategy, AllocationStrategy

    if isinstance(strategy, OverlayStrategy):
        # Walk down to find the innermost allocation strategy
        underlying = strategy.underlying
        while isinstance(underlying, OverlayStrategy):
            underlying = underlying.underlying

        # Run underlying allocation first
        underlying_results = engine.run_backtest(
            strategy=underlying,
            historical_data=prices,
            start_date=backtest_start,
            end_date=backtest_end
        )

        # Run with overlay transformations
        return engine.run_backtest_with_overlay(
            underlying_strategy=underlying,
            overlay_strategy=strategy,
            historical_data=prices,
            underlying_results=underlying_results,
            start_date=backtest_start,
            end_date=backtest_end
        )
    else:
        return engine.run_backtest(
            strategy=strategy,
            historical_data=prices,
            start_date=backtest_start,
            end_date=backtest_end
        )


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
                primary_strategy = loader.build_composed_strategy(args.composed_strategy)
                strategy_display = args.composed_strategy
            else:
                # Load allocation + underlying + overlays
                primary_strategy = loader.build_strategy(args.strategy)
                strategy_display = STRATEGY_REGISTRY.get(
                    args.strategy, {}
                ).get('display_name', args.strategy)

            benchmark_strategy = loader.build_strategy(args.benchmark)
            benchmark_display = STRATEGY_REGISTRY.get(
                args.benchmark, {}
            ).get('display_name', args.benchmark)

            logger.info(f"✓ Loaded strategies from definitions")
        except Exception as e:
            logger.error(f"Failed to load strategies from definitions: {e}")
            raise
    else:
        # Use traditional registry-based approach
        strategy_display = STRATEGY_REGISTRY[args.strategy]['display_name']
        benchmark_display = STRATEGY_REGISTRY[args.benchmark]['display_name']

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

    # Run backtests
    if args.all:
        # Run all available strategies
        all_strategy_results = await run_all_strategies(args, prices, backtest_start, backtest_end)

        # Save individual results to separate files
        logger.info("\n" + "=" * 60)
        logger.info("SAVING INDIVIDUAL STRATEGY RESULTS")
        logger.info("=" * 60)

        # Create subdirectories for organization
        strategies_dir = RESULTS_DIR / 'strategies'
        strategies_dir.mkdir(exist_ok=True)

        strategy_index = {}

        for strategy_key, result_data in all_strategy_results.items():
            # Create directory for this strategy
            strategy_dir = strategies_dir / strategy_key
            strategy_dir.mkdir(exist_ok=True)

            # Save portfolio history as JSON
            import pandas as pd
            portfolio_history = result_data['portfolio_history']
            portfolio_json_path = strategy_dir / 'portfolio_history.json'
            with open(portfolio_json_path, 'w') as f:
                json.dump(portfolio_history, f, indent=2)

            # Save transactions
            transactions_json_path = strategy_dir / 'transactions.json'
            with open(transactions_json_path, 'w') as f:
                json.dump(result_data['transactions'], f, indent=2)

            # Save weights history
            weights_json_path = strategy_dir / 'weights_history.json'
            with open(weights_json_path, 'w') as f:
                json.dump(result_data['weights_history'], f, indent=2)

            # Save metrics
            metrics_json_path = strategy_dir / 'metrics.json'
            with open(metrics_json_path, 'w') as f:
                json.dump(result_data['metrics'], f, indent=2)

            # Save strategy info
            info_json_path = strategy_dir / 'info.json'
            with open(info_json_path, 'w') as f:
                json.dump(result_data['info'], f, indent=2)

            logger.info(f"✓ Saved results for {strategy_key} to {strategy_dir}")

            # Add to index
            strategy_index[strategy_key] = {
                'path': str(strategy_dir.relative_to(RESULTS_DIR)),
                'metrics': result_data['metrics'],
                'info': result_data['info']
            }

        # Save master index
        index_path = RESULTS_DIR / 'strategies_index.json'
        index_data = {
            'run_date': datetime.now().isoformat(),
            'total_strategies': len(strategy_index),
            'strategies': strategy_index,
            'config': {
                'symbols': SYMBOLS,
                'currency': CURRENCY,
                'initial_capital': INITIAL_CAPITAL,
                'transaction_cost_bps': TRANSACTION_COST_BPS,
                'rebalance_frequency': REBALANCE_FREQUENCY,
                'lookback_days': LOOKBACK_DAYS
            }
        }
        with open(index_path, 'w') as f:
            json.dump(index_data, f, indent=2)
        logger.info(f"✓ Strategies index saved to: {index_path}")

        # Print summary
        logger.info("\n" + "=" * 60)
        logger.info("BACKTEST SUMMARY")
        logger.info("=" * 60)
        for strategy_key, result_data in sorted(all_strategy_results.items()):
            metrics = result_data['metrics']
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
            lookback_days=LOOKBACK_DAYS
        )

        # Run primary strategy backtest
        logger.info(f"\nRunning {strategy_display} backtest...")
        primary_results = _run_strategy(
            engine, primary_strategy, prices, backtest_start, backtest_end
        )

        # Generate metrics
        generate_metrics_summary(primary_results)
        logger.info(f"  {strategy_display} backtest complete")
        logger.info(f"  - Rebalances: {len(primary_results.portfolio_history)}")
        logger.info(f"  - Transactions: {len(primary_results.transactions)}")
        logger.info(f"  - Final value: {primary_results.final_value:,.2f}")

        # Run benchmark strategy backtest
        logger.info(f"\nRunning {benchmark_display} backtest...")
        benchmark_results = _run_strategy(
            engine, benchmark_strategy, prices, backtest_start, backtest_end
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
        if args.use_definitions:
            if args.composed_strategy:
                primary_info = {
                    'name': args.composed_strategy,
                    'display_name': strategy_display,
                    'type': 'composed',
                    'params': None
                }
                benchmark_info = None
            else:
                primary_info = {
                    'name': args.strategy,
                    'display_name': strategy_display,
                    'type': 'definition',
                    'params': None
                }
                benchmark_info = {
                    'name': args.benchmark,
                    'display_name': benchmark_display,
                    'type': 'definition',
                    'params': None
                }
        else:
            strategy_params = extract_strategy_params(args, args.strategy)
            benchmark_params = extract_strategy_params(args, args.benchmark)
            primary_info = {
                'name': args.strategy,
                'display_name': strategy_display,
                'type': 'registry',
                'params': strategy_params
            }
            benchmark_info = {
                'name': args.benchmark,
                'display_name': benchmark_display,
                'type': 'registry',
                'params': benchmark_params
            }

        metadata = {
            'primary_strategy': primary_info,
            'benchmark_strategy': benchmark_info,
            'run_date': datetime.now().isoformat(),
            'strategy_mode': 'definitions' if args.use_definitions else 'registry',
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
Examples (Run ALL Strategies - RECOMMENDED):
  python run_backtest.py --all                              # Run all strategies, separate result files
  python run_backtest.py --all --refresh                    # Force fresh data from IB

Examples (Single Strategy vs Benchmark - Traditional):
  python run_backtest.py --use-definitions --strategy trend_following --benchmark hrp_ward
  python run_backtest.py --use-definitions --composed-strategy trend_with_vol_12
  python run_backtest.py --strategy hrp --benchmark equal_weight
  python run_backtest.py --strategy equal_weight --benchmark hrp --refresh

List Available Strategies:
  python -c "from strategies.strategy_loader import StrategyLoader; loader = StrategyLoader(); loader.list_strategies()"
        """
    )

    # Mode selection
    parser.add_argument(
        '--all',
        action='store_true',
        help='Run ALL available strategies from strategy definitions and output separate results files. '
             'This is the recommended mode for comprehensive analysis.'
    )

    # Strategy loading mode
    parser.add_argument(
        '--use-definitions',
        action='store_true',
        help='Load strategies from YAML definitions (strategy_definitions/) instead of registry'
    )

    # Strategy selection
    parser.add_argument(
        '--strategy',
        type=str,
        default='hrp',
        help='Primary strategy to test (default: hrp). '
             'When --use-definitions is set, this is a YAML definition key (e.g., trend_following). '
             'Otherwise, this is a registry strategy name.'
    )

    parser.add_argument(
        '--benchmark',
        type=str,
        default='equal_weight',
        help='Benchmark strategy for comparison (default: equal_weight). '
             'When --use-definitions is set, this is a YAML definition key. '
             'Otherwise, this is a registry strategy name.'
    )

    parser.add_argument(
        '--composed-strategy',
        type=str,
        default=None,
        help='Use a composed strategy instead of primary/benchmark. '
             'Only works with --use-definitions. '
             'Example: --use-definitions --composed-strategy trend_with_vol_12'
    )

    # Data refresh flag
    parser.add_argument(
        '--refresh',
        action='store_true',
        help='Force fresh data from Interactive Brokers (skip cache). '
             'Useful for getting the latest market data.'
    )

    # Strategy-specific parameters (dynamically generated for registry mode)
    # Only add these if not using YAML definitions
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
    if not args.all:
        # Only validate these if not running all strategies
        if args.composed_strategy is None and args.strategy == args.benchmark:
            parser.error("Strategy and benchmark must be different (unless using --composed-strategy)")

        if args.composed_strategy and not args.use_definitions:
            parser.error("--composed-strategy requires --use-definitions")

    # Run the async main function
    asyncio.run(main(args))
