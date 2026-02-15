"""
Test script for HRP backtest using synthetic data.

This script demonstrates that the HRP strategy and backtesting system
works correctly by using simulated price data for the 4 UK ETFs.
"""

import numpy as np
import pandas as pd
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Strategy imports
from strategies import HRPStrategy, EqualWeightStrategy

# Backtesting imports
from backtesting import BacktestEngine

# Analytics imports
from analytics import generate_metrics_summary, plot_portfolio_comparison, create_performance_table

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
SYMBOLS = ['VUSA', 'SSLN', 'SGLN', 'IWRD']
INITIAL_CAPITAL = 10000.0  # GBP
TRANSACTION_COST_BPS = 7.5
REBALANCE_FREQUENCY = 'monthly'
LOOKBACK_DAYS = 252  # 1 year for HRP calculation

# Output paths
RESULTS_DIR = Path('results')
RESULTS_DIR.mkdir(exist_ok=True)


def generate_synthetic_price_data(symbols, days=1500, start_price=100.0):
    """
    Generate synthetic price data for testing.

    Args:
        symbols: List of symbol names
        days: Number of trading days to generate
        start_price: Starting price for all symbols

    Returns:
        DataFrame with columns=symbols, index=dates, values=prices
    """
    logger.info(f"Generating synthetic price data for {len(symbols)} symbols over {days} days")

    # Generate dates (trading days only, skip weekends)
    dates = pd.bdate_range(end=datetime.now(), periods=days)
    actual_days = len(dates)

    # Generate synthetic prices with different volatility and correlation patterns
    np.random.seed(42)  # For reproducibility

    prices_dict = {}
    returns_prev = None

    for i, symbol in enumerate(symbols):
        # Different drift and volatility for each symbol
        drifts = [0.0001, 0.00005, 0.00008, 0.00012]
        volatilities = [0.015, 0.012, 0.018, 0.010]

        drift = drifts[i]
        volatility = volatilities[i]

        # Generate returns with some correlation
        returns = np.random.normal(drift, volatility, actual_days)

        # Add some correlation between symbols
        if returns_prev is not None:
            returns = 0.7 * returns + 0.3 * returns_prev

        # Calculate prices from returns
        prices = start_price * np.exp(np.cumsum(returns))
        prices_dict[symbol] = prices
        returns_prev = returns

    prices_df = pd.DataFrame(prices_dict, index=dates)

    logger.info(
        f"✓ Generated synthetic data: {len(prices_df)} days, "
        f"{prices_df.index[0].date()} to {prices_df.index[-1].date()}"
    )

    return prices_df


def main():
    """Main execution function."""
    print("\n" + "=" * 60)
    print("HIERARCHICAL RISK PARITY BACKTEST - SYNTHETIC DATA TEST")
    print("=" * 60)
    print(f"Symbols: {', '.join(SYMBOLS)}")
    print(f"Currency: GBP (Simulated)")
    print(f"Initial Capital: £{INITIAL_CAPITAL:,.2f}")
    print(f"Transaction Cost: {TRANSACTION_COST_BPS} basis points")
    print(f"Rebalance Frequency: {REBALANCE_FREQUENCY}")
    print(f"Lookback Period: {LOOKBACK_DAYS} days (1 year)")
    print("=" * 60 + "\n")

    # Generate synthetic data
    prices = generate_synthetic_price_data(SYMBOLS)

    # Validate data
    logger.info(f"Data range: {prices.index[0].date()} to {prices.index[-1].date()}")
    logger.info(f"Total trading days: {len(prices)}")

    # Determine backtest date range
    # Need LOOKBACK_DAYS before first rebalance
    backtest_start = prices.index[LOOKBACK_DAYS]
    backtest_end = prices.index[-1]

    logger.info(
        f"\nBacktest period: {backtest_start.date()} to {backtest_end.date()}"
    )
    logger.info(f"Backtest days: {len(prices[backtest_start:])} days")

    # Initialize strategies
    logger.info("\n" + "=" * 60)
    logger.info("RUNNING BACKTESTS")
    logger.info("=" * 60)

    hrp_strategy = HRPStrategy(linkage_method='single')
    ew_strategy = EqualWeightStrategy()

    # Initialize backtest engine
    engine = BacktestEngine(
        initial_capital=INITIAL_CAPITAL,
        transaction_cost_bps=TRANSACTION_COST_BPS,
        rebalance_frequency=REBALANCE_FREQUENCY,
        lookback_days=LOOKBACK_DAYS
    )

    # Run HRP backtest
    logger.info("\nRunning HRP Strategy backtest...")
    hrp_results = engine.run_backtest(
        strategy=hrp_strategy,
        historical_data=prices,
        start_date=backtest_start,
        end_date=backtest_end
    )

    # Generate HRP metrics
    generate_metrics_summary(hrp_results)
    logger.info(f"✓ HRP backtest complete")
    logger.info(f"  - Rebalances: {len(hrp_results.portfolio_history)}")
    logger.info(f"  - Transactions: {len(hrp_results.transactions)}")
    logger.info(f"  - Final value: £{hrp_results.final_value:,.2f}")

    # Run Equal Weight backtest
    logger.info("\nRunning Equal Weight Strategy backtest...")
    ew_results = engine.run_backtest(
        strategy=ew_strategy,
        historical_data=prices,
        start_date=backtest_start,
        end_date=backtest_end
    )

    # Generate EW metrics
    generate_metrics_summary(ew_results)
    logger.info(f"✓ Equal Weight backtest complete")
    logger.info(f"  - Rebalances: {len(ew_results.portfolio_history)}")
    logger.info(f"  - Transactions: {len(ew_results.transactions)}")
    logger.info(f"  - Final value: £{ew_results.final_value:,.2f}")

    # Performance Summary
    logger.info("\n" + "=" * 60)
    logger.info("PERFORMANCE SUMMARY")
    logger.info("=" * 60)

    results_dict = {
        'HRP Strategy': hrp_results,
        'Equal Weight': ew_results
    }

    # Create performance table
    perf_table = create_performance_table(results_dict)
    print("\n" + str(perf_table))

    # Save results
    logger.info("\n" + "=" * 60)
    logger.info("SAVING RESULTS")
    logger.info("=" * 60)

    # Save portfolio histories
    hrp_history_path = RESULTS_DIR / 'hrp_portfolio_history.csv'
    hrp_results.portfolio_history.to_csv(hrp_history_path)
    logger.info(f"✓ HRP portfolio history saved to: {hrp_history_path}")

    ew_history_path = RESULTS_DIR / 'ew_portfolio_history.csv'
    ew_results.portfolio_history.to_csv(ew_history_path)
    logger.info(f"✓ Equal Weight portfolio history saved to: {ew_history_path}")

    # Save transactions
    hrp_tx_df = pd.DataFrame([
        {
            'timestamp': t.timestamp,
            'symbol': t.symbol,
            'quantity': t.quantity,
            'price': t.price,
            'cost': t.total_cost
        }
        for t in hrp_results.transactions
    ])
    hrp_tx_path = RESULTS_DIR / 'hrp_transactions.csv'
    hrp_tx_df.to_csv(hrp_tx_path, index=False)
    logger.info(f"✓ HRP transactions saved to: {hrp_tx_path}")

    ew_tx_df = pd.DataFrame([
        {
            'timestamp': t.timestamp,
            'symbol': t.symbol,
            'quantity': t.quantity,
            'price': t.price,
            'cost': t.total_cost
        }
        for t in ew_results.transactions
    ])
    ew_tx_path = RESULTS_DIR / 'ew_transactions.csv'
    ew_tx_df.to_csv(ew_tx_path, index=False)
    logger.info(f"✓ Equal Weight transactions saved to: {ew_tx_path}")

    # Save performance metrics
    perf_table_path = RESULTS_DIR / 'performance_comparison.csv'
    perf_table.to_csv(perf_table_path)
    logger.info(f"✓ Performance table saved to: {perf_table_path}")

    # Create and save visualization
    logger.info("\nGenerating performance charts...")
    fig = plot_portfolio_comparison(
        results_dict,
        save_path=str(RESULTS_DIR / 'performance_charts.png')
    )
    logger.info(f"✓ Performance charts saved to: {RESULTS_DIR / 'performance_charts.png'}")

    # Display summary statistics
    logger.info("\n" + "=" * 60)
    logger.info("BACKTEST COMPLETE - SUMMARY")
    logger.info("=" * 60)

    print("\n[HRP Strategy Performance]")
    print(f"   Initial Capital:    £{hrp_results.initial_capital:,.2f}")
    print(f"   Final Value:        £{hrp_results.final_value:,.2f}")
    print(f"   Total Return:       {hrp_results.metrics['total_return']:.2f}%")
    print(f"   CAGR:               {hrp_results.metrics['cagr']:.2f}%")
    print(f"   Sharpe Ratio:       {hrp_results.metrics['sharpe_ratio']:.3f}")
    print(f"   Max Drawdown:       {hrp_results.metrics['max_drawdown']:.2f}%")
    print(f"   Volatility:         {hrp_results.metrics['volatility']:.2f}%")

    print("\n[Equal Weight Strategy Performance]")
    print(f"   Initial Capital:    £{ew_results.initial_capital:,.2f}")
    print(f"   Final Value:        £{ew_results.final_value:,.2f}")
    print(f"   Total Return:       {ew_results.metrics['total_return']:.2f}%")
    print(f"   CAGR:               {ew_results.metrics['cagr']:.2f}%")
    print(f"   Sharpe Ratio:       {ew_results.metrics['sharpe_ratio']:.3f}")
    print(f"   Max Drawdown:       {ew_results.metrics['max_drawdown']:.2f}%")
    print(f"   Volatility:         {ew_results.metrics['volatility']:.2f}%")

    # Calculate outperformance
    hrp_return = hrp_results.metrics['total_return']
    ew_return = ew_results.metrics['total_return']
    outperformance = hrp_return - ew_return

    print("\n[Performance Comparison]")
    print(f"   HRP Outperformance: {outperformance:+.2f}%")
    if outperformance > 0:
        print(f"   [OUTPERFORMED] HRP beat equal weight by {abs(outperformance):.2f}%")
    else:
        print(f"   [UNDERPERFORMED] HRP underperformed by {abs(outperformance):.2f}%")

    print(f"\n[Results saved to: {RESULTS_DIR.absolute()}]")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
