"""
CLI script for parameter optimization of trading strategies.

Usage:
    # Parameter sweep
    python scripts/run_optimization.py --strategy hrp --param linkage_method=single,complete,ward

    # Walk-forward analysis
    python scripts/run_optimization.py --strategy trend_following \
        --param lookback_days=252,504 --param half_life_days=30,60,90 \
        --walk-forward --in-sample 756 --out-of-sample 252

    # Optimize with custom metric
    python scripts/run_optimization.py --strategy hrp \
        --param linkage_method=single,complete,ward \
        --metric sortino_ratio
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from strategies import (
    HRPStrategy, TrendFollowingStrategy, EqualWeightStrategy,
    MinimumVarianceStrategy, RiskParityStrategy, MomentumTopNStrategy,
    AssetStrategy
)
from optimization import ParameterSweep, WalkForwardAnalysis
from data import HistoricalDataCache, align_dataframes

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Strategy class mapping
STRATEGY_CLASSES = {
    'hrp': HRPStrategy,
    'trend_following': TrendFollowingStrategy,
    'equal_weight': EqualWeightStrategy,
    'minimum_variance': MinimumVarianceStrategy,
    'risk_parity': RiskParityStrategy,
    'momentum': MomentumTopNStrategy,
}

# Default UK ETF assets
SYMBOLS = ['VUSA', 'SSLN', 'SGLN', 'IWRD']
CURRENCY = 'GBP'


def parse_param(param_str: str) -> tuple:
    """Parse 'key=val1,val2,val3' into (key, [val1, val2, val3])."""
    key, values_str = param_str.split('=', 1)
    values = values_str.split(',')

    # Try to convert to appropriate types
    parsed_values = []
    for v in values:
        v = v.strip()
        try:
            parsed_values.append(int(v))
        except ValueError:
            try:
                parsed_values.append(float(v))
            except ValueError:
                parsed_values.append(v)

    return key, parsed_values


def load_cached_prices() -> pd.DataFrame:
    """Load prices from cache."""
    cache = HistoricalDataCache(cache_dir='data/cache')
    data_dict = {}

    for symbol in SYMBOLS:
        df = cache.load_cached_data(
            symbol,
            pd.Timestamp('2015-01-01'),
            pd.Timestamp.now(),
            max_age_days=30
        )
        if not df.empty:
            data_dict[symbol] = df

    if not data_dict:
        logger.error("No cached data found. Run a backtest first: python scripts/run_backtest.py --all")
        sys.exit(1)

    return align_dataframes(data_dict)


def main():
    parser = argparse.ArgumentParser(
        description="Strategy parameter optimization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run_optimization.py --strategy hrp --param linkage_method=single,complete,ward
  python scripts/run_optimization.py --strategy trend_following --param lookback_days=252,504 --param half_life_days=30,60,90
  python scripts/run_optimization.py --strategy hrp --param linkage_method=single,complete,ward --walk-forward
        """
    )

    parser.add_argument(
        '--strategy', type=str, required=True,
        choices=list(STRATEGY_CLASSES.keys()),
        help='Strategy to optimize'
    )
    parser.add_argument(
        '--param', type=str, action='append', required=True,
        help='Parameter to sweep: key=val1,val2,val3 (can specify multiple --param flags)'
    )
    parser.add_argument(
        '--metric', type=str, default='sharpe_ratio',
        help='Metric to optimize (default: sharpe_ratio)'
    )
    parser.add_argument(
        '--walk-forward', action='store_true',
        help='Run walk-forward analysis instead of simple parameter sweep'
    )
    parser.add_argument(
        '--in-sample', type=int, default=756,
        help='In-sample window size in trading days (default: 756 = ~3 years)'
    )
    parser.add_argument(
        '--out-of-sample', type=int, default=252,
        help='Out-of-sample window size in trading days (default: 252 = ~1 year)'
    )
    parser.add_argument(
        '--output', type=str, default=None,
        help='Output CSV file path (default: results/optimization_<strategy>.csv)'
    )

    args = parser.parse_args()

    # Parse parameters
    param_grid = {}
    for param_str in args.param:
        key, values = parse_param(param_str)
        param_grid[key] = values

    strategy_class = STRATEGY_CLASSES[args.strategy]

    print("\n" + "=" * 60)
    print("STRATEGY PARAMETER OPTIMIZATION")
    print("=" * 60)
    print(f"Strategy: {args.strategy}")
    print(f"Parameter Grid: {param_grid}")
    print(f"Target Metric: {args.metric}")
    print(f"Mode: {'Walk-Forward' if args.walk_forward else 'Parameter Sweep'}")
    if args.walk_forward:
        print(f"In-Sample: {args.in_sample} days, Out-of-Sample: {args.out_of_sample} days")
    print("=" * 60 + "\n")

    # Load prices
    logger.info("Loading cached price data...")
    prices = load_cached_prices()
    logger.info(f"Loaded {len(prices)} days for {list(prices.columns)}")

    # Create underlying assets
    underlying = [AssetStrategy(s, currency=CURRENCY) for s in SYMBOLS]

    # Determine backtest range
    lookback = 252
    backtest_start = prices.index[lookback]
    backtest_end = prices.index[-1]

    if args.walk_forward:
        # Walk-forward analysis
        wfa = WalkForwardAnalysis(
            strategy_class=strategy_class,
            param_grid=param_grid,
            in_sample_days=args.in_sample,
            out_of_sample_days=args.out_of_sample,
            metric=args.metric,
            initial_capital=10000.0,
            transaction_cost_bps=7.5
        )

        results = wfa.run(underlying=underlying, prices=prices)

        print("\n" + "=" * 60)
        print("WALK-FORWARD RESULTS")
        print("=" * 60)
        print(f"\nWindows: {len(results.windows)}")
        print(f"Avg In-Sample {args.metric}: {results.avg_in_sample:.4f}")
        print(f"Avg Out-of-Sample {args.metric}: {results.avg_out_sample:.4f}")
        print(f"Overfitting Ratio: {results.overfitting_ratio:.2f}x")
        print(f"\n(Ratio close to 1.0 = robust, >> 1.0 = overfit)\n")

        if not results.summary_df.empty:
            print(results.summary_df.to_string(index=False))

            output_path = args.output or f'results/walk_forward_{args.strategy}.csv'
            Path(output_path).parent.mkdir(exist_ok=True)
            results.summary_df.to_csv(output_path, index=False)
            print(f"\nResults saved to: {output_path}")

    else:
        # Simple parameter sweep
        sweep = ParameterSweep(
            strategy_class=strategy_class,
            param_grid=param_grid,
            metric=args.metric,
            initial_capital=10000.0,
            transaction_cost_bps=7.5
        )

        results_df = sweep.run(
            underlying=underlying,
            prices=prices,
            start_date=backtest_start,
            end_date=backtest_end,
            lookback_days=lookback
        )

        if results_df.empty:
            print("\nNo valid results. Check your parameter grid and data.")
            return

        print("\n" + "=" * 60)
        print("PARAMETER SWEEP RESULTS")
        print("=" * 60)
        print(f"\nSorted by: {args.metric} (descending)\n")
        print(results_df.to_string(index=False))

        output_path = args.output or f'results/param_sweep_{args.strategy}.csv'
        Path(output_path).parent.mkdir(exist_ok=True)
        results_df.to_csv(output_path, index=False)
        print(f"\nResults saved to: {output_path}")


if __name__ == '__main__':
    main()
