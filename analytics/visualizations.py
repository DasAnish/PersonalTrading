"""
Visualization functions for backtest results.

This module provides functions to create charts and plots for portfolio
backtest performance analysis.
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from typing import Dict
from backtesting.engine import BacktestResults
from .metrics import calculate_drawdown, calculate_return_attribution


def plot_portfolio_comparison(
    results_dict: Dict[str, BacktestResults],
    figsize: tuple = (14, 14),
    save_path: str = None
) -> plt.Figure:
    """
    Create comparison plot for multiple backtest results.

    Creates a 5-panel figure showing:
    1. Portfolio value over time
    2. Drawdown over time
    3. Portfolio weights over time (for first strategy)
    4. Return attribution by asset (for first strategy)
    5. Performance metrics table

    Args:
        results_dict: Dict mapping strategy name to BacktestResults
        figsize: Figure size (width, height)
        save_path: If provided, save figure to this path

    Returns:
        matplotlib Figure object

    Example:
        >>> results = {
        ...     'HRP': hrp_results,
        ...     'Equal Weight': ew_results
        ... }
        >>> fig = plot_portfolio_comparison(results, save_path='backtest.png')
    """
    # Create figure with 5 subplots
    fig, axes = plt.subplots(5, 1, figsize=figsize)
    fig.suptitle('Portfolio Strategy Comparison', fontsize=16, fontweight='bold')

    # Color palette
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']

    # Panel 1: Portfolio Value
    ax1 = axes[0]
    for i, (name, results) in enumerate(results_dict.items()):
        history = results.portfolio_history
        ax1.plot(
            history.index,
            history['total_value'],
            label=name,
            color=colors[i % len(colors)],
            linewidth=2
        )

    # Add individual ETF benchmarks (fully invested in each ETF)
    if len(results_dict) > 0:
        first_results = list(results_dict.values())[0]
        initial_capital = first_results.initial_capital
        history = first_results.portfolio_history

        # Extract ETF prices and calculate individual ETF performance
        etf_colors = ['#ff9999', '#99ccff', '#99ff99', '#ffcc99']
        etf_index = 0

        for col in history.columns:
            if col.endswith('_value'):
                symbol = col.replace('_value', '')
                qty_col = f'{symbol}_qty'

                if qty_col in history.columns:
                    # Calculate price at each point: price = position_value / position_qty
                    # When qty is 0, we'll use the previous known price
                    qty_series = history[qty_col].astype(float)
                    value_series = history[col].astype(float)

                    # Calculate prices where we have positions
                    prices = pd.Series(index=history.index, dtype=float)
                    for idx in history.index:
                        if qty_series[idx] > 0:
                            prices[idx] = value_series[idx] / qty_series[idx]

                    # Forward fill prices to handle gaps when qty is 0
                    prices = prices.ffill()

                    # Find the first date where we have a price
                    valid_prices = prices[prices.notna()]
                    if len(valid_prices) > 0:
                        first_price_date = valid_prices.index[0]
                        first_price = valid_prices.iloc[0]

                        # Calculate what full investment in this ETF would return
                        # portfolio_value = initial_capital * (price_at_date / first_price)
                        etf_values = pd.Series(
                            initial_capital * (prices / first_price),
                            index=history.index
                        )

                        # Plot only from the first price onwards
                        etf_values_valid = etf_values[first_price_date:]
                        if len(etf_values_valid) > 1:
                            ax1.plot(
                                etf_values_valid.index,
                                etf_values_valid,
                                label=f'{symbol} (100%)',
                                color=etf_colors[etf_index % len(etf_colors)],
                                linewidth=2,
                                linestyle='-',
                                alpha=1.0
                            )
                        etf_index += 1

        # Add initial capital baseline
        ax1.axhline(
            y=initial_capital,
            color='gray',
            linestyle='--',
            linewidth=1,
            alpha=0.5,
            label='Initial Capital'
        )

    ax1.set_ylabel('Portfolio Value (£)', fontsize=12)
    ax1.set_title('Portfolio Value Over Time (with Individual ETF Benchmarks)', fontsize=14, fontweight='bold')
    ax1.legend(loc='best', fontsize=9)
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha='right')

    # Panel 2: Drawdown
    ax2 = axes[1]
    for i, (name, results) in enumerate(results_dict.items()):
        history = results.portfolio_history
        drawdown = calculate_drawdown(history['total_value']) * 100  # Convert to %

        ax2.fill_between(
            history.index,
            drawdown,
            0,
            alpha=0.3,
            color=colors[i % len(colors)],
            label=name
        )
        ax2.plot(
            history.index,
            drawdown,
            color=colors[i % len(colors)],
            linewidth=1.5
        )

    ax2.set_ylabel('Drawdown (%)', fontsize=12)
    ax2.set_title('Drawdown Over Time', fontsize=14, fontweight='bold')
    ax2.legend(loc='best', fontsize=10)
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')

    # Panel 3: Portfolio Weights Over Time (for first strategy)
    ax3 = axes[2]
    first_name = list(results_dict.keys())[0]
    first_results = results_dict[first_name]

    if not first_results.weights_history.empty:
        weights_df = first_results.weights_history
        # Create stacked area chart of weights
        ax3.stackplot(
            weights_df.index,
            *[weights_df[col] * 100 for col in weights_df.columns],
            labels=weights_df.columns,
            alpha=0.8
        )
        ax3.set_ylabel('Weight (%)', fontsize=12)
        ax3.set_title(f'Portfolio Weights Over Time - {first_name}', fontsize=14, fontweight='bold')
        ax3.legend(loc='center left', bbox_to_anchor=(1, 0.5), fontsize=9)
        ax3.set_ylim(0, 100)
        ax3.grid(True, alpha=0.3)
        ax3.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45, ha='right')
    else:
        ax3.text(0.5, 0.5, 'No weights history available',
                ha='center', va='center', transform=ax3.transAxes)
        ax3.set_title(f'Portfolio Weights Over Time - {first_name}', fontsize=14, fontweight='bold')
        ax3.axis('off')

    # Panel 4: Return Attribution by Asset
    ax4 = axes[3]
    attribution = calculate_return_attribution(first_results.portfolio_history)

    if not attribution.empty and len(attribution.columns) > 0:
        # Plot return contribution of each asset over time
        for col in attribution.columns:
            ax4.plot(
                attribution.index,
                attribution[col],
                label=col,
                linewidth=2
            )
        ax4.axhline(y=0, color='black', linestyle='-', linewidth=0.5, alpha=0.5)
        ax4.set_ylabel('Return Contribution (£)', fontsize=12)
        ax4.set_title(f'Return Attribution by Asset - {first_name}', fontsize=14, fontweight='bold')
        ax4.legend(loc='best', fontsize=9)
        ax4.grid(True, alpha=0.3)
        ax4.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        plt.setp(ax4.xaxis.get_majorticklabels(), rotation=45, ha='right')
    else:
        ax4.text(0.5, 0.5, 'No return attribution data available',
                ha='center', va='center', transform=ax4.transAxes)
        ax4.set_title(f'Return Attribution by Asset - {first_name}', fontsize=14, fontweight='bold')
        ax4.axis('off')

    # Panel 5: Performance Metrics Table
    ax5 = axes[4]
    ax5.axis('tight')
    ax5.axis('off')

    # Prepare metrics table
    metrics_data = []
    metrics_labels = [
        'Total Return (%)',
        'CAGR (%)',
        'Sharpe Ratio',
        'Max Drawdown (%)',
        'Volatility (%)',
        'Total Transactions',
        'Total Costs (£)',
        'Final Value (£)'
    ]

    for name, results in results_dict.items():
        metrics = results.metrics
        row = [
            f"{metrics.get('total_return', 0):.2f}",
            f"{metrics.get('cagr', 0):.2f}",
            f"{metrics.get('sharpe_ratio', 0):.3f}",
            f"{metrics.get('max_drawdown', 0):.2f}",
            f"{metrics.get('volatility', 0):.2f}",
            f"{metrics.get('total_transactions', 0):.0f}",
            f"{metrics.get('total_transaction_costs', 0):.2f}",
            f"{metrics.get('final_value', 0):.2f}"
        ]
        metrics_data.append(row)

    # Create table
    table = ax5.table(
        cellText=metrics_data,
        rowLabels=list(results_dict.keys()),
        colLabels=metrics_labels,
        cellLoc='center',
        rowLoc='center',
        loc='center',
        bbox=[0, 0, 1, 1]
    )

    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 2)

    # Style table
    for i in range(len(metrics_labels)):
        cell = table[(0, i)]
        cell.set_facecolor('#40466e')
        cell.set_text_props(weight='bold', color='white')

    for i in range(len(results_dict)):
        cell = table[(i + 1, -1)]
        cell.set_facecolor('#f0f0f0')
        cell.set_text_props(weight='bold')

    ax5.set_title('Performance Metrics Summary', fontsize=14, fontweight='bold', pad=20)

    # Adjust layout
    plt.tight_layout()

    # Save if path provided
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"Figure saved to: {save_path}")

    return fig


def plot_transaction_analysis(
    results: BacktestResults,
    figsize: tuple = (12, 6),
    save_path: str = None
) -> plt.Figure:
    """
    Create transaction analysis plot.

    Shows transaction frequency and costs over time.

    Args:
        results: BacktestResults object
        figsize: Figure size
        save_path: Optional path to save figure

    Returns:
        matplotlib Figure object
    """
    transactions = results.transactions

    if not transactions:
        print("No transactions to plot")
        return None

    # Create DataFrame from transactions
    tx_df = pd.DataFrame([
        {
            'date': t.timestamp,
            'symbol': t.symbol,
            'quantity': t.quantity,
            'cost': t.total_cost
        }
        for t in transactions
    ])

    # Group by date
    daily_costs = tx_df.groupby('date')['cost'].sum()
    daily_count = tx_df.groupby('date').size()

    # Create figure
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize)
    fig.suptitle(f'Transaction Analysis - {results.strategy_name}', fontsize=14, fontweight='bold')

    # Plot transaction costs
    ax1.bar(daily_costs.index, daily_costs.values, color='#d62728', alpha=0.7)
    ax1.set_ylabel('Transaction Costs (£)', fontsize=11)
    ax1.set_title('Transaction Costs Over Time', fontsize=12)
    ax1.grid(True, alpha=0.3)

    # Plot transaction count
    ax2.bar(daily_count.index, daily_count.values, color='#1f77b4', alpha=0.7)
    ax2.set_ylabel('Number of Transactions', fontsize=11)
    ax2.set_xlabel('Date', fontsize=11)
    ax2.set_title('Transaction Frequency', fontsize=12)
    ax2.grid(True, alpha=0.3)

    # Format dates
    for ax in [ax1, ax2]:
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"Transaction analysis saved to: {save_path}")

    return fig


def create_performance_table(results_dict: Dict[str, BacktestResults]) -> pd.DataFrame:
    """
    Create performance metrics table as DataFrame.

    Args:
        results_dict: Dict mapping strategy name to BacktestResults

    Returns:
        DataFrame with strategies as columns and metrics as rows

    Example:
        >>> table = create_performance_table(results_dict)
        >>> print(table)
                              HRP  Equal Weight
        Total Return (%)    42.30         36.80
        CAGR (%)             7.30          6.50
        Sharpe Ratio         1.18          0.98
        ...
    """
    metrics_dict = {}

    for name, results in results_dict.items():
        metrics = results.metrics
        metrics_dict[name] = {
            'Total Return (%)': f"{metrics.get('total_return', 0):.2f}",
            'CAGR (%)': f"{metrics.get('cagr', 0):.2f}",
            'Sharpe Ratio': f"{metrics.get('sharpe_ratio', 0):.3f}",
            'Max Drawdown (%)': f"{metrics.get('max_drawdown', 0):.2f}",
            'Volatility (%)': f"{metrics.get('volatility', 0):.2f}",
            'Total Transactions': f"{metrics.get('total_transactions', 0):.0f}",
            'Total Costs (£)': f"{metrics.get('total_transaction_costs', 0):.2f}",
            'Final Value (£)': f"{metrics.get('final_value', 0):.2f}"
        }

    df = pd.DataFrame(metrics_dict)

    return df
