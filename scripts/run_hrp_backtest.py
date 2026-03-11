"""
DEPRECATED: This script is deprecated in favor of run_backtest.py

This wrapper maintains backward compatibility by forwarding to the new generic script.
It will be removed in a future version. Please use run_backtest.py instead.

Usage (deprecated):
    python run_hrp_backtest.py              # Use cached data (faster)
    python run_hrp_backtest.py --refresh    # Force fresh data from IB (slower)

New usage:
    python run_backtest.py                                    # Default: HRP vs Equal Weight
    python run_backtest.py --refresh                          # Force fresh data from IB
    python run_backtest.py --strategy equal_weight --benchmark hrp
"""

import sys
import warnings
import argparse
import asyncio

# Show deprecation warning
warnings.warn(
    "run_hrp_backtest.py is deprecated. Please use run_backtest.py instead. "
    "The new script supports flexible strategy selection via --strategy and --benchmark arguments.",
    DeprecationWarning,
    stacklevel=2
)

# Import from the new script
from run_backtest import main

if __name__ == "__main__":
    # Parse arguments and forward to new script
    parser = argparse.ArgumentParser(
        description="Run HRP backtest on UK ETFs (DEPRECATED - use run_backtest.py instead)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples (deprecated):
  python run_hrp_backtest.py              # Use cached data (faster)
  python run_hrp_backtest.py --refresh    # Force fresh data from IB (slower)

Equivalent new commands:
  python run_backtest.py                  # Default: HRP vs Equal Weight
  python run_backtest.py --refresh        # Force fresh data from IB
        """
    )
    parser.add_argument(
        '--refresh',
        action='store_true',
        help='Force fresh data from Interactive Brokers (skip cache)'
    )
    args = parser.parse_args()

    # Create args object with defaults for new arguments
    class Args:
        strategy = 'hrp'
        benchmark = 'equal_weight'
        refresh = args.refresh

    # Run the async main function with new arguments
    asyncio.run(main(Args()))
