#!/usr/bin/env python3
"""
Interactive web dashboard for portfolio strategy backtest results.

Supports multiple strategies with dynamic labels loaded from metadata.json.

Run with: python scripts/serve_results.py
Then visit: http://localhost:5000
"""

import json
import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from flask import Flask, jsonify, render_template_string

# Configuration
BASE_DIR = Path(__file__).parent.parent
RESULTS_DIR = BASE_DIR / "results"

app = Flask(__name__, static_folder=None)

# Global metadata (loaded at startup)
METADATA = None


def load_metadata():
    """
    Load metadata from metadata.json.

    Returns metadata dict with strategy names and parameters.
    Falls back to defaults if metadata.json doesn't exist.
    """
    metadata_path = RESULTS_DIR / 'metadata.json'

    if metadata_path.exists():
        try:
            with open(metadata_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"   [!] Error loading metadata.json: {e}")
            print(f"   [*] Using default metadata (HRP vs Equal Weight)")

    # Default fallback for backward compatibility
    return {
        'primary_strategy': {
            'name': 'hrp',
            'display_name': 'Hierarchical Risk Parity',
            'params': {'linkage_method': 'single'}
        },
        'benchmark_strategy': {
            'name': 'equal_weight',
            'display_name': 'Equal Weight',
            'params': {}
        },
        'run_date': datetime.now().isoformat(),
        'config': {}
    }


def get_file_mappings(metadata):
    """
    Get file prefix mappings from metadata.

    Returns dict mapping display names to file prefixes.
    """
    return {
        metadata['primary_strategy']['display_name']: "hrp",
        metadata['benchmark_strategy']['display_name']: "ew"
    }


def load_results():
    """Load all backtest results from CSV files."""
    global METADATA
    results = {}

    print(f"\n[*] Looking for results in: {RESULTS_DIR}")
    print(f"   Files available: {list(RESULTS_DIR.glob('*.csv'))}\n")

    # Load metadata first
    METADATA = load_metadata()
    file_mappings = get_file_mappings(METADATA)

    print(f"   [*] Metadata loaded:")
    print(f"       Primary: {METADATA['primary_strategy']['display_name']}")
    print(f"       Benchmark: {METADATA['benchmark_strategy']['display_name']}\n")

    # Load performance comparison
    perf_file = RESULTS_DIR / "performance_comparison.csv"
    if perf_file.exists():
        print(f"   [+] Loaded metrics from {perf_file.name}")
        df = pd.read_csv(perf_file, index_col=0)
        results["metrics"] = df.to_dict()
    else:
        print(f"   [-] Metrics file not found: {perf_file.name}")

    # Load portfolio histories
    for strategy_display, prefix in file_mappings.items():
        key = strategy_display.lower().replace(" ", "_")
        file_path = RESULTS_DIR / f"{prefix}_portfolio_history.csv"

        if file_path.exists():
            print(f"   [+] Loaded {strategy_display} history from {file_path.name}")
            df = pd.read_csv(file_path)
            df["timestamp"] = pd.to_datetime(df["timestamp"].tolist())
            results[f"{key}_history"] = df
        else:
            print(f"   [-] {strategy_display} history not found: {file_path.name}")

    # Load transactions
    for strategy_display, prefix in file_mappings.items():
        key = strategy_display.lower().replace(" ", "_")
        file_path = RESULTS_DIR / f"{prefix}_transactions.csv"

        if file_path.exists():
            print(f"   [+] Loaded {strategy_display} transactions from {file_path.name}")
            df = pd.read_csv(file_path)
            results[f"{key}_transactions"] = df
        else:
            print(f"   [-] {strategy_display} transactions not found: {file_path.name}")

    print()
    return results


def get_portfolio_value_data(results):
    """Extract portfolio value time series."""
    data = {}

    primary_name = METADATA['primary_strategy']['display_name']
    benchmark_name = METADATA['benchmark_strategy']['display_name']

    primary_key = primary_name.lower().replace(" ", "_")
    benchmark_key = benchmark_name.lower().replace(" ", "_")

    if f"{primary_key}_history" in results:
        df = results[f"{primary_key}_history"]
        data[primary_name] = {
            "dates": df["timestamp"].dt.strftime("%Y-%m-%d").tolist(),
            "values": df["total_value"].tolist(),
        }

    if f"{benchmark_key}_history" in results:
        df = results[f"{benchmark_key}_history"]
        data[benchmark_name] = {
            "dates": df["timestamp"].dt.strftime("%Y-%m-%d").tolist(),
            "values": df["total_value"].tolist(),
        }

    return data


def get_drawdown_data(results):
    """Calculate and return drawdown data."""
    data = {}

    primary_name = METADATA['primary_strategy']['display_name']
    benchmark_name = METADATA['benchmark_strategy']['display_name']

    primary_key = primary_name.lower().replace(" ", "_")
    benchmark_key = benchmark_name.lower().replace(" ", "_")

    for key, label in [(f"{primary_key}_history", primary_name), (f"{benchmark_key}_history", benchmark_name)]:
        if key in results:
            df = results[key].copy()
            df["running_max"] = df["total_value"].cummax()
            df["drawdown"] = ((df["total_value"] - df["running_max"]) / df["running_max"]) * 100

            data[label] = {
                "dates": df["timestamp"].dt.strftime("%Y-%m-%d").tolist(),
                "drawdown": df["drawdown"].tolist(),
            }

    return data


def get_weights_data(results):
    """Extract portfolio weights over time."""
    data = {}

    primary_name = METADATA['primary_strategy']['display_name']
    primary_key = primary_name.lower().replace(" ", "_")

    if f"{primary_key}_history" in results:
        df = results[f"{primary_key}_history"].copy()
        df["timestamp"] = df["timestamp"].dt.strftime("%Y-%m-%d")

        # Calculate weights
        symbols = [col.replace("_qty", "") for col in df.columns if col.endswith("_qty")]
        weights_data = {"dates": df["timestamp"].tolist()}

        for symbol in symbols:
            value_col = f"{symbol}_value"
            if value_col in df.columns:
                weights_data[symbol] = (
                    (df[value_col] / df["total_value"]) * 100
                ).fillna(0).tolist()

        data[primary_name] = weights_data

    return data


def get_attribution_data(results):
    """Calculate daily attribution: previous weights × asset returns."""
    data = {}

    primary_name = METADATA['primary_strategy']['display_name']
    benchmark_name = METADATA['benchmark_strategy']['display_name']

    primary_key = primary_name.lower().replace(" ", "_")
    benchmark_key = benchmark_name.lower().replace(" ", "_")

    for key, label in [(f"{primary_key}_history", primary_name), (f"{benchmark_key}_history", benchmark_name)]:
        if key in results:
            df = results[key].copy()
            df = df.reset_index(drop=True)

            # Get symbols
            symbols = [col.replace("_qty", "") for col in df.columns if col.endswith("_qty")]

            attribution_data = {"dates": [], "symbols": symbols}

            # Initialize attribution lists for each symbol
            for symbol in symbols:
                attribution_data[symbol] = []

            # Calculate daily attribution for each day
            for i in range(1, len(df)):
                prev_row = df.iloc[i - 1]
                curr_row = df.iloc[i]

                # Calculate previous day's weights
                prev_total = prev_row["total_value"]
                if prev_total <= 0:
                    continue

                attribution_data["dates"].append(curr_row["timestamp"].strftime("%Y-%m-%d"))

                for symbol in symbols:
                    prev_value_col = f"{symbol}_value"
                    curr_value_col = f"{symbol}_value"

                    if prev_value_col in df.columns and curr_value_col in df.columns:
                        prev_value = prev_row[prev_value_col]
                        curr_value = curr_row[curr_value_col]

                        # Handle missing values
                        if pd.isna(prev_value) or pd.isna(curr_value) or prev_value == 0:
                            daily_attribution = 0
                        else:
                            # Weight at T-1
                            weight_t_minus_1 = (prev_value / prev_total) * 100
                            # Return from T-1 to T
                            asset_return = ((curr_value - prev_value) / prev_value) * 100
                            # Attribution = weight * return
                            daily_attribution = (weight_t_minus_1 / 100) * asset_return

                        attribution_data[symbol].append(daily_attribution)

            data[label] = attribution_data

    return data


def get_transactions_data(results):
    """Extract transaction data."""
    data = {}

    primary_name = METADATA['primary_strategy']['display_name']
    benchmark_name = METADATA['benchmark_strategy']['display_name']

    primary_key = primary_name.lower().replace(" ", "_")
    benchmark_key = benchmark_name.lower().replace(" ", "_")

    if f"{primary_key}_transactions" in results:
        df = results[f"{primary_key}_transactions"].copy()
        # Rename columns if needed
        if "cost" in df.columns and "transaction_cost" not in df.columns:
            df["transaction_cost"] = df["cost"]
        if "cost" in df.columns and "total_cost" not in df.columns:
            df["total_cost"] = df["cost"] * df["quantity"] * df["price"]
        data[primary_name] = df.to_dict("records")

    if f"{benchmark_key}_transactions" in results:
        df = results[f"{benchmark_key}_transactions"].copy()
        # Rename columns if needed
        if "cost" in df.columns and "transaction_cost" not in df.columns:
            df["transaction_cost"] = df["cost"]
        if "cost" in df.columns and "total_cost" not in df.columns:
            df["total_cost"] = df["cost"] * df["quantity"] * df["price"]
        data[benchmark_name] = df.to_dict("records")

    return data


def get_metrics_table(results):
    """Format metrics for display."""
    if "metrics" not in results:
        return {}

    df = pd.DataFrame(results["metrics"])
    metrics = {}

    # Transpose to have metrics as rows and strategies as columns
    for idx in df.index:
        metrics[idx] = {}
        for col in df.columns:
            value = df.loc[idx, col]
            # Format nicely
            if isinstance(value, float):
                # Handle NaN and inf values
                if pd.isna(value) or np.isinf(value):
                    metrics[idx][col] = "N/A"
                elif "Return" in idx or "CAGR" in idx or "Drawdown" in idx or "Volatility" in idx:
                    metrics[idx][col] = f"{value:.2f}%"
                elif "Ratio" in idx or "Turnover" in idx:
                    if "Turnover" in idx:
                        metrics[idx][col] = f"{value:.6f}"
                    else:
                        metrics[idx][col] = f"{value:.3f}"
                else:
                    metrics[idx][col] = f"{value:.2f}"
            else:
                metrics[idx][col] = str(value)

    return metrics


@app.route("/")
def index():
    """Serve the main dashboard page."""
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Strategy Backtest Dashboard</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.min.js"></script>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }

            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }

            .container {
                max-width: 1400px;
                margin: 0 auto;
                background: white;
                border-radius: 12px;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                overflow: hidden;
            }

            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 40px 30px;
                text-align: center;
            }

            .header h1 {
                font-size: 2.5em;
                margin-bottom: 10px;
            }

            .header p {
                font-size: 1.1em;
                opacity: 0.9;
            }

            .tabs {
                display: flex;
                border-bottom: 2px solid #e0e0e0;
                background: #f5f5f5;
            }

            .tab-button {
                flex: 1;
                padding: 20px;
                border: none;
                background: none;
                cursor: pointer;
                font-size: 1em;
                font-weight: 500;
                color: #666;
                transition: all 0.3s ease;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }

            .tab-button:hover {
                background: #e8e8e8;
                color: #667eea;
            }

            .tab-button.active {
                color: #667eea;
                border-bottom: 3px solid #667eea;
                margin-bottom: -2px;
            }

            .content {
                padding: 30px;
            }

            .tab-panel {
                display: none;
            }

            .tab-panel.active {
                display: block;
                animation: fadeIn 0.3s ease;
            }

            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }

            .chart-container {
                position: relative;
                height: 400px;
                margin-bottom: 30px;
            }

            .metrics-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }

            .metric-card {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            }

            .metric-card h3 {
                font-size: 0.9em;
                text-transform: uppercase;
                opacity: 0.9;
                margin-bottom: 10px;
            }

            .metric-card .value {
                font-size: 2em;
                font-weight: bold;
            }

            .metrics-table {
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 30px;
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            }

            .metrics-table thead {
                background: #667eea;
                color: white;
            }

            .metrics-table th {
                padding: 15px;
                text-align: left;
                font-weight: 600;
            }

            .metrics-table td {
                padding: 12px 15px;
                border-bottom: 1px solid #e0e0e0;
            }

            .metrics-table tbody tr:hover {
                background: #f9f9f9;
            }

            .metrics-table tbody tr:last-child td {
                border-bottom: none;
            }

            .positive {
                color: #28a745;
                font-weight: 600;
            }

            .negative {
                color: #dc3545;
                font-weight: 600;
            }

            .transactions-table {
                width: 100%;
                border-collapse: collapse;
                font-size: 0.95em;
            }

            .transactions-table thead {
                background: #f0f0f0;
            }

            .transactions-table th {
                padding: 12px;
                text-align: left;
                font-weight: 600;
                color: #333;
                border-bottom: 2px solid #ddd;
            }

            .transactions-table td {
                padding: 10px 12px;
                border-bottom: 1px solid #e0e0e0;
            }

            .transactions-table tbody tr:hover {
                background: #f9f9f9;
            }

            .loading {
                text-align: center;
                padding: 40px;
                color: #666;
            }

            .error {
                background: #fff3cd;
                color: #856404;
                padding: 20px;
                border-radius: 8px;
                margin-bottom: 20px;
            }

            .comparison-charts {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }

            .comparison-chart-container {
                position: relative;
                height: 250px;
                background: #f9f9f9;
                padding: 15px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            }

            .view-toggle-btn {
                padding: 10px 20px;
                margin-right: 10px;
                border: 2px solid #667eea;
                background: white;
                color: #667eea;
                border-radius: 6px;
                cursor: pointer;
                font-weight: 600;
                transition: all 0.3s ease;
            }

            .view-toggle-btn:hover {
                background: #f0f4ff;
            }

            .view-toggle-btn.active {
                background: #667eea;
                color: white;
            }

            .attribution-container {
                margin-top: 20px;
            }

            @media (max-width: 768px) {
                .header h1 {
                    font-size: 1.8em;
                }

                .tabs {
                    flex-wrap: wrap;
                }

                .tab-button {
                    flex: 1 1 50%;
                    padding: 15px;
                }

                .metrics-grid {
                    grid-template-columns: 1fr;
                }

                .chart-container {
                    height: 300px;
                }

                .attribution-container {
                    grid-template-columns: 1fr !important;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📊 Strategy Backtest Dashboard</h1>
                <p>Interactive visualization of portfolio optimization results</p>
            </div>

            <div class="tabs">
                <button class="tab-button active" onclick="showTab('overview')">Overview</button>
                <button class="tab-button" onclick="showTab('portfolio')">Portfolio Value</button>
                <button class="tab-button" onclick="showTab('drawdown')">Drawdown</button>
                <button class="tab-button" onclick="showTab('weights')">Weights</button>
                <button class="tab-button" onclick="showTab('attribution')">Attribution</button>
                <button class="tab-button" onclick="showTab('transactions')">Transactions</button>
            </div>

            <div class="content">
                <!-- Overview Tab -->
                <div id="overview" class="tab-panel active">
                    <h2>Performance Metrics</h2>
                    <table class="metrics-table" id="metricsTable">
                        <thead>
                            <tr>
                                <th>Metric</th>
                                <th>Strategy</th>
                                <th>Equal Weight</th>
                            </tr>
                        </thead>
                        <tbody id="metricsBody">
                            <tr><td colspan="3" class="loading">Loading...</td></tr>
                        </tbody>
                    </table>

                    <h2 style="margin-top: 40px;">Key Metrics Comparison</h2>
                    <div class="metrics-grid" id="metricsGrid"></div>
                </div>

                <!-- Portfolio Value Tab -->
                <div id="portfolio" class="tab-panel">
                    <h2>Portfolio Value Over Time</h2>
                    <div class="chart-container">
                        <canvas id="portfolioChart"></canvas>
                    </div>
                </div>

                <!-- Drawdown Tab -->
                <div id="drawdown" class="tab-panel">
                    <h2>Drawdown Analysis</h2>
                    <div class="chart-container">
                        <canvas id="drawdownChart"></canvas>
                    </div>
                </div>

                <!-- Weights Tab -->
                <div id="weights" class="tab-panel">
                    <h2>Strategy Portfolio Weights Over Time</h2>
                    <div style="margin-bottom: 20px;">
                        <button onclick="toggleWeightsMode('cumulative')" id="weightsModeCumulative" class="view-toggle-btn active">Cumulative View</button>
                        <button onclick="toggleWeightsMode('individual')" id="weightsModIndividual" class="view-toggle-btn">Individual Assets</button>
                    </div>
                    <div class="chart-container">
                        <canvas id="weightsChart"></canvas>
                    </div>
                </div>

                <!-- Attribution Tab -->
                <div id="attribution" class="tab-panel">
                    <h2>Daily Attribution Analysis</h2>
                    <p style="margin-bottom: 20px; color: #666;">Daily attribution calculated as: T-1 portfolio weight × asset return (T-1 to T)</p>
                    <div class="attribution-container">
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                            <div>
                                <h3>Strategy Attribution</h3>
                                <div class="chart-container" style="margin-top: 10px;">
                                    <canvas id="attributionStrategyChart"></canvas>
                                </div>
                            </div>
                            <div>
                                <h3>Equal Weight Attribution</h3>
                                <div class="chart-container" style="margin-top: 10px;">
                                    <canvas id="attributionEWChart"></canvas>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Transactions Tab -->
                <div id="transactions" class="tab-panel">
                    <h2>Transaction History</h2>
                    <h3 style="margin-top: 30px; margin-bottom: 15px;">Strategy Transactions</h3>
                    <table class="transactions-table" id="strategyTransactionsTable">
                        <thead>
                            <tr>
                                <th>Date</th>
                                <th>Symbol</th>
                                <th>Quantity</th>
                                <th>Price</th>
                                <th>Total</th>
                                <th>Cost</th>
                            </tr>
                        </thead>
                        <tbody id="strategyTransactionsBody">
                            <tr><td colspan="6">No transactions</td></tr>
                        </tbody>
                    </table>

                    <h3 style="margin-top: 30px; margin-bottom: 15px;">Equal Weight Transactions</h3>
                    <table class="transactions-table" id="ewTransactionsTable">
                        <thead>
                            <tr>
                                <th>Date</th>
                                <th>Symbol</th>
                                <th>Quantity</th>
                                <th>Price</th>
                                <th>Total</th>
                                <th>Cost</th>
                            </tr>
                        </thead>
                        <tbody id="ewTransactionsBody">
                            <tr><td colspan="6" class="loading">Loading...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <script>
            let charts = {};
            let weightsMode = 'cumulative';
            let weightsData = null;

            async function loadData() {
                try {
                    const response = await fetch('/api/data');
                    const data = await response.json();

                    weightsData = data.weights;
                    displayMetrics(data.metrics);
                    displayPortfolioChart(data.portfolio_value);
                    displayDrawdownChart(data.drawdown);
                    displayWeightsChart(data.weights);
                    displayAttributionCharts(data.attribution);
                    displayTransactions(data.transactions);
                } catch (error) {
                    console.error('Error loading data:', error);
                    document.querySelector('.error') || alert('Error loading data');
                }
            }

            function displayMetrics(metrics) {
                const tbody = document.getElementById('metricsBody');
                tbody.innerHTML = '';

                for (const [metric, values] of Object.entries(metrics)) {
                    const row = document.createElement('tr');
                    const strategyValue = values['Strategy'] || 'N/A';
                    const ewValue = values['Equal Weight'] || 'N/A';

                    row.innerHTML = `
                        <td><strong>${metric}</strong></td>
                        <td class="${isPositive(strategyValue) ? 'positive' : 'negative'}">${strategyValue}</td>
                        <td class="${isPositive(ewValue) ? 'positive' : 'negative'}">${ewValue}</td>
                    `;
                    tbody.appendChild(row);
                }

                // Display key metrics as cards
                const grid = document.getElementById('metricsGrid');
                grid.innerHTML = '';

                const keyMetrics = ['Total Return (%)', 'Sharpe Ratio', 'Max Drawdown (%)', 'Volatility (%)', 'Omega Ratio'];
                for (const metric of keyMetrics) {
                    if (metrics[metric]) {
                        const card = document.createElement('div');
                        card.className = 'metric-card';
                        card.innerHTML = `
                            <h3>${metric}</h3>
                            <div class="value" style="color: #4ade80;">Strategy: ${metrics[metric]['Strategy']}</div>
                            <div class="value" style="color: #f87171; margin-top: 10px;">EW: ${metrics[metric]['Equal Weight']}</div>
                        `;
                        grid.appendChild(card);
                    }
                }
            }

            function displayPortfolioChart(data) {
                const ctx = document.getElementById('portfolioChart').getContext('2d');

                if (charts.portfolio) charts.portfolio.destroy();

                const datasets = [];

                // Add Strategy data if available
                if (data.Strategy && data.Strategy.values && data.Strategy.values.length > 0) {
                    datasets.push({
                        label: 'Strategy',
                        data: data.Strategy.values,
                        borderColor: '#667eea',
                        backgroundColor: 'rgba(102, 126, 234, 0.1)',
                        tension: 0.4,
                        pointRadius: 0,
                        borderWidth: 2,
                    });
                }

                // Add Equal Weight data if available
                if (data['Equal Weight'] && data['Equal Weight'].values && data['Equal Weight'].values.length > 0) {
                    datasets.push({
                        label: 'Equal Weight',
                        data: data['Equal Weight'].values,
                        borderColor: '#f59e0b',
                        backgroundColor: 'rgba(245, 158, 11, 0.1)',
                        tension: 0.4,
                        pointRadius: 0,
                        borderWidth: 2,
                    });
                }

                charts.portfolio = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: data.Strategy ? data.Strategy.dates : (data['Equal Weight'] ? data['Equal Weight'].dates : []),
                        datasets: datasets
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                display: true,
                                position: 'top',
                            }
                        },
                        scales: {
                            y: {
                                beginAtZero: false,
                            }
                        }
                    }
                });
            }

            function displayDrawdownChart(data) {
                const ctx = document.getElementById('drawdownChart').getContext('2d');

                if (charts.drawdown) charts.drawdown.destroy();

                const datasets = [];

                // Add Strategy data if available
                if (data.Strategy && data.Strategy.drawdown && data.Strategy.drawdown.length > 0) {
                    datasets.push({
                        label: 'Strategy',
                        data: data.Strategy.drawdown,
                        borderColor: '#667eea',
                        backgroundColor: 'rgba(102, 126, 234, 0.2)',
                        tension: 0.4,
                        pointRadius: 0,
                        borderWidth: 2,
                        fill: true,
                    });
                }

                // Add Equal Weight data if available
                if (data['Equal Weight'] && data['Equal Weight'].drawdown && data['Equal Weight'].drawdown.length > 0) {
                    datasets.push({
                        label: 'Equal Weight',
                        data: data['Equal Weight'].drawdown,
                        borderColor: '#f59e0b',
                        backgroundColor: 'rgba(245, 158, 11, 0.2)',
                        tension: 0.4,
                        pointRadius: 0,
                        borderWidth: 2,
                        fill: true,
                    });
                }

                charts.drawdown = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: data.Strategy ? data.Strategy.dates : (data['Equal Weight'] ? data['Equal Weight'].dates : []),
                        datasets: datasets
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                display: true,
                                position: 'top',
                            }
                        },
                        scales: {
                            y: {
                                max: 0,
                                ticks: {
                                    callback: function(value) {
                                        return value + '%';
                                    }
                                }
                            }
                        }
                    }
                });
            }

            function displayWeightsChart(data) {
                if (!data.Strategy || !data.Strategy.dates || data.Strategy.dates.length === 0) {
                    document.getElementById('weightsChart').parentElement.innerHTML = '<p>Weights data not available</p>';
                    return;
                }

                renderWeightsChart(data);
            }

            function renderWeightsChart(data) {
                const ctx = document.getElementById('weightsChart').getContext('2d');

                if (charts.weights) charts.weights.destroy();

                // Extract symbols (skip dates)
                const symbols = Object.keys(data.Strategy).filter(k => k !== 'dates');
                const colors = ['#667eea', '#764ba2', '#f59e0b', '#ec4899'];

                const datasets = symbols.map((symbol, idx) => ({
                    label: symbol,
                    data: data.Strategy[symbol] || [],
                    backgroundColor: colors[idx % colors.length],
                    borderColor: colors[idx % colors.length],
                    pointRadius: 0,
                    borderWidth: weightsMode === 'individual' ? 2 : 0,
                    fill: weightsMode === 'cumulative',
                    tension: 0.2
                }));

                if (datasets.length === 0) {
                    document.getElementById('weightsChart').parentElement.innerHTML = '<p>No weights data available</p>';
                    return;
                }

                charts.weights = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: data.Strategy.dates,
                        datasets: datasets
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                stacked: weightsMode === 'cumulative',
                                max: 100,
                                ticks: {
                                    callback: function(value) {
                                        return value + '%';
                                    }
                                }
                            }
                        },
                        plugins: {
                            filler: {
                                propagate: true
                            },
                            legend: {
                                display: true,
                                position: 'top'
                            }
                        }
                    }
                });
            }

            function toggleWeightsMode(mode) {
                weightsMode = mode;

                // Update button states
                document.getElementById('weightsModeCumulative').classList.remove('active');
                document.getElementById('weightsModIndividual').classList.remove('active');

                if (mode === 'cumulative') {
                    document.getElementById('weightsModeCumulative').classList.add('active');
                } else {
                    document.getElementById('weightsModIndividual').classList.add('active');
                }

                // Re-render chart
                if (weightsData) {
                    renderWeightsChart(weightsData);
                }
            }

            function displayAttributionCharts(data) {
                if (!data) return;

                // Display Strategy Attribution
                if (data.Strategy && data.Strategy.dates && data.Strategy.dates.length > 0) {
                    const strategyCtx = document.getElementById('attributionStrategyChart').getContext('2d');
                    if (charts.attributionStrategy) charts.attributionStrategy.destroy();

                    const symbols = data.Strategy.symbols || [];
                    const colors = ['#667eea', '#764ba2', '#f59e0b', '#ec4899'];
                    const datasets = symbols.map((symbol, idx) => ({
                        label: symbol,
                        data: data.Strategy[symbol] || [],
                        borderColor: colors[idx % colors.length],
                        backgroundColor: colors[idx % colors.length],
                        pointRadius: 0,
                        borderWidth: 1,
                        tension: 0.2
                    }));

                    charts.attributionStrategy = new Chart(strategyCtx, {
                        type: 'line',
                        data: {
                            labels: data.Strategy.dates,
                            datasets: datasets
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            scales: {
                                y: {
                                    ticks: {
                                        callback: function(value) {
                                            return value.toFixed(2) + '%';
                                        }
                                    }
                                }
                            },
                            plugins: {
                                legend: {
                                    display: true,
                                    position: 'top'
                                }
                            }
                        }
                    });
                }

                // Display Equal Weight Attribution
                if (data['Equal Weight'] && data['Equal Weight'].dates && data['Equal Weight'].dates.length > 0) {
                    const ewCtx = document.getElementById('attributionEWChart').getContext('2d');
                    if (charts.attributionEW) charts.attributionEW.destroy();

                    const symbols = data['Equal Weight'].symbols || [];
                    const colors = ['#667eea', '#764ba2', '#f59e0b', '#ec4899'];
                    const datasets = symbols.map((symbol, idx) => ({
                        label: symbol,
                        data: data['Equal Weight'][symbol] || [],
                        borderColor: colors[idx % colors.length],
                        backgroundColor: colors[idx % colors.length],
                        pointRadius: 0,
                        borderWidth: 1,
                        tension: 0.2
                    }));

                    charts.attributionEW = new Chart(ewCtx, {
                        type: 'line',
                        data: {
                            labels: data['Equal Weight'].dates,
                            datasets: datasets
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            scales: {
                                y: {
                                    ticks: {
                                        callback: function(value) {
                                            return value.toFixed(2) + '%';
                                        }
                                    }
                                }
                            },
                            plugins: {
                                legend: {
                                    display: true,
                                    position: 'top'
                                }
                            }
                        }
                    });
                }
            }

            function displayTransactions(data) {
                // Strategy Transactions
                const strategyBody = document.getElementById('strategyTransactionsBody');
                strategyBody.innerHTML = '';
                if (data.Strategy && data.Strategy.length > 0) {
                    data.Strategy.forEach(tx => {
                        const row = document.createElement('tr');
                        const quantity = tx.quantity || 0;
                        const price = tx.price || 0;
                        const tradeValue = Math.abs(quantity * price);
                        const cost = tx.transaction_cost || tx.cost || 0;

                        row.innerHTML = `
                            <td>${tx.timestamp}</td>
                            <td>${tx.symbol}</td>
                            <td>${quantity.toFixed(0)}</td>
                            <td>£${price.toFixed(2)}</td>
                            <td>£${tradeValue.toFixed(2)}</td>
                            <td>£${cost.toFixed(4)}</td>
                        `;
                        strategyBody.appendChild(row);
                    });
                } else {
                    strategyBody.innerHTML = '<tr><td colspan="6">No transactions</td></tr>';
                }

                // Equal Weight Transactions
                const ewBody = document.getElementById('ewTransactionsBody');
                ewBody.innerHTML = '';
                if (data['Equal Weight'] && data['Equal Weight'].length > 0) {
                    data['Equal Weight'].forEach(tx => {
                        const row = document.createElement('tr');
                        const quantity = tx.quantity || 0;
                        const price = tx.price || 0;
                        const tradeValue = Math.abs(quantity * price);
                        const cost = tx.transaction_cost || tx.cost || 0;

                        row.innerHTML = `
                            <td>${tx.timestamp}</td>
                            <td>${tx.symbol}</td>
                            <td>${quantity.toFixed(0)}</td>
                            <td>£${price.toFixed(2)}</td>
                            <td>£${tradeValue.toFixed(2)}</td>
                            <td>£${cost.toFixed(4)}</td>
                        `;
                        ewBody.appendChild(row);
                    });
                } else {
                    ewBody.innerHTML = '<tr><td colspan="6">No transactions</td></tr>';
                }
            }

            function showTab(tabName) {
                // Hide all panels
                document.querySelectorAll('.tab-panel').forEach(panel => {
                    panel.classList.remove('active');
                });

                // Remove active class from all buttons
                document.querySelectorAll('.tab-button').forEach(btn => {
                    btn.classList.remove('active');
                });

                // Show selected panel
                document.getElementById(tabName).classList.add('active');

                // Add active class to clicked button
                event.target.classList.add('active');
            }

            function isPositive(value) {
                if (typeof value === 'string') {
                    if (value === 'N/A' || value === 'nan') return false;
                    const num = parseFloat(value);
                    return !isNaN(num) && num > 0;
                }
                return typeof value === 'number' && !isNaN(value) && value > 0;
            }

            // Load data on page load
            document.addEventListener('DOMContentLoaded', loadData);
        </script>
    </body>
    </html>
    """

    return render_template_string(html)


def normalize_strategy_keys(data_dict):
    """
    Normalize strategy names in data dictionary for backward compatibility.

    Converts display names back to generic "Strategy" and "Equal Weight" keys
    for compatibility with existing JavaScript code.
    """
    if not data_dict or not METADATA:
        return data_dict

    primary_name = METADATA['primary_strategy']['display_name']
    benchmark_name = METADATA['benchmark_strategy']['display_name']

    normalized = {}
    for key, value in data_dict.items():
        if key == primary_name:
            normalized['Strategy'] = value
        elif key == benchmark_name:
            normalized['Equal Weight'] = value
        else:
            normalized[key] = value

    return normalized


@app.route("/api/data")
def api_data():
    """API endpoint to serve all dashboard data as JSON."""
    try:
        results = load_results()

        # Debug: Log what was loaded
        print(f"Loaded results keys: {list(results.keys())}")

        if not results:
            return jsonify({"error": "No backtest results found. Run the backtest first: python scripts/run_backtest.py"}), 400

        # Get data with dynamic labels
        data = {
            "metrics": get_metrics_table(results),
            "portfolio_value": normalize_strategy_keys(get_portfolio_value_data(results)),
            "drawdown": normalize_strategy_keys(get_drawdown_data(results)),
            "weights": normalize_strategy_keys(get_weights_data(results)),
            "attribution": normalize_strategy_keys(get_attribution_data(results)),
            "transactions": normalize_strategy_keys(get_transactions_data(results)),
            "metadata": {
                "primary_strategy": METADATA['primary_strategy']['display_name'],
                "benchmark_strategy": METADATA['benchmark_strategy']['display_name']
            }
        }

        return jsonify(data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Error loading data: {str(e)}"}), 500


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Strategy Backtest Dashboard")
    print("=" * 60)
    print("\n[*] Starting server...\n")
    print("[*] Open your browser and navigate to: http://localhost:5000\n")
    print("Press Ctrl+C to stop the server\n")
    print("=" * 60 + "\n")

    app.run(debug=True, port=5000)
