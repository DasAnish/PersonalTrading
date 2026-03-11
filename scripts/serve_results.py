#!/usr/bin/env python3
"""
Interactive web dashboard for HRP backtest results.

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


def load_results():
    """Load all backtest results from CSV files."""
    results = {}

    print(f"\n[*] Looking for results in: {RESULTS_DIR}")
    print(f"   Files available: {list(RESULTS_DIR.glob('*.csv'))}\n")

    # Load performance comparison
    perf_file = RESULTS_DIR / "performance_comparison.csv"
    if perf_file.exists():
        print(f"   [+] Loaded metrics from {perf_file.name}")
        df = pd.read_csv(perf_file, index_col=0)
        results["metrics"] = df.to_dict()
    else:
        print(f"   [-] Metrics file not found: {perf_file.name}")

    # Load portfolio histories
    file_mappings = {
        "HRP Strategy": "hrp",
        "Equal Weight": "ew"
    }

    for strategy, prefix in file_mappings.items():
        key = strategy.lower().replace(" ", "_")
        file_path = RESULTS_DIR / f"{prefix}_portfolio_history.csv"

        if file_path.exists():
            print(f"   [+] Loaded {strategy} history from {file_path.name}")
            df = pd.read_csv(file_path)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            results[f"{key}_history"] = df
        else:
            print(f"   [-] {strategy} history not found: {file_path.name}")

    # Load transactions
    for strategy, prefix in file_mappings.items():
        key = strategy.lower().replace(" ", "_")
        file_path = RESULTS_DIR / f"{prefix}_transactions.csv"

        if file_path.exists():
            print(f"   [+] Loaded {strategy} transactions from {file_path.name}")
            df = pd.read_csv(file_path)
            results[f"{key}_transactions"] = df
        else:
            print(f"   [-] {strategy} transactions not found: {file_path.name}")

    print()
    return results


def get_portfolio_value_data(results):
    """Extract portfolio value time series."""
    data = {}

    if "hrp_strategy_history" in results:
        df = results["hrp_strategy_history"]
        data["HRP"] = {
            "dates": df["timestamp"].dt.strftime("%Y-%m-%d").tolist(),
            "values": df["total_value"].tolist(),
        }

    if "equal_weight_history" in results:
        df = results["equal_weight_history"]
        data["Equal Weight"] = {
            "dates": df["timestamp"].dt.strftime("%Y-%m-%d").tolist(),
            "values": df["total_value"].tolist(),
        }

    return data


def get_drawdown_data(results):
    """Calculate and return drawdown data."""
    data = {}

    for key, label in [("hrp_strategy_history", "HRP"), ("equal_weight_history", "Equal Weight")]:
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

    if "hrp_strategy_history" in results:
        df = results["hrp_strategy_history"].copy()
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

        data["HRP"] = weights_data

    return data


def get_transactions_data(results):
    """Extract transaction data."""
    data = {}

    if "hrp_strategy_transactions" in results:
        df = results["hrp_strategy_transactions"].copy()
        # Rename columns if needed
        if "cost" in df.columns and "transaction_cost" not in df.columns:
            df["transaction_cost"] = df["cost"]
        if "cost" in df.columns and "total_cost" not in df.columns:
            df["total_cost"] = df["cost"] * df["quantity"] * df["price"]
        data["HRP"] = df.to_dict("records")

    if "equal_weight_transactions" in results:
        df = results["equal_weight_transactions"].copy()
        # Rename columns if needed
        if "cost" in df.columns and "transaction_cost" not in df.columns:
            df["transaction_cost"] = df["cost"]
        if "cost" in df.columns and "total_cost" not in df.columns:
            df["total_cost"] = df["cost"] * df["quantity"] * df["price"]
        data["Equal Weight"] = df.to_dict("records")

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
        <title>HRP Backtest Dashboard</title>
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
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📊 HRP Backtest Dashboard</h1>
                <p>Interactive visualization of portfolio optimization results</p>
            </div>

            <div class="tabs">
                <button class="tab-button active" onclick="showTab('overview')">Overview</button>
                <button class="tab-button" onclick="showTab('portfolio')">Portfolio Value</button>
                <button class="tab-button" onclick="showTab('drawdown')">Drawdown</button>
                <button class="tab-button" onclick="showTab('weights')">Weights</button>
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
                                <th>HRP Strategy</th>
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
                    <h2>HRP Portfolio Weights Over Time</h2>
                    <div class="chart-container">
                        <canvas id="weightsChart"></canvas>
                    </div>
                </div>

                <!-- Transactions Tab -->
                <div id="transactions" class="tab-panel">
                    <h2>Transaction History</h2>
                    <h3 style="margin-top: 30px; margin-bottom: 15px;">HRP Strategy Transactions</h3>
                    <table class="transactions-table" id="hrpTransactionsTable">
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
                        <tbody id="hrpTransactionsBody">
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

            async function loadData() {
                try {
                    const response = await fetch('/api/data');
                    const data = await response.json();

                    displayMetrics(data.metrics);
                    displayPortfolioChart(data.portfolio_value);
                    displayDrawdownChart(data.drawdown);
                    displayWeightsChart(data.weights);
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
                    const hrpValue = values['HRP Strategy'] || 'N/A';
                    const ewValue = values['Equal Weight'] || 'N/A';

                    row.innerHTML = `
                        <td><strong>${metric}</strong></td>
                        <td class="${isPositive(hrpValue) ? 'positive' : 'negative'}">${hrpValue}</td>
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
                            <div class="value" style="color: #4ade80;">HRP: ${metrics[metric]['HRP Strategy']}</div>
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

                // Add HRP data if available
                if (data.HRP && data.HRP.values && data.HRP.values.length > 0) {
                    datasets.push({
                        label: 'HRP Strategy',
                        data: data.HRP.values,
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
                        labels: data.HRP ? data.HRP.dates : (data['Equal Weight'] ? data['Equal Weight'].dates : []),
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

                // Add HRP data if available
                if (data.HRP && data.HRP.drawdown && data.HRP.drawdown.length > 0) {
                    datasets.push({
                        label: 'HRP Strategy',
                        data: data.HRP.drawdown,
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
                        labels: data.HRP ? data.HRP.dates : (data['Equal Weight'] ? data['Equal Weight'].dates : []),
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
                if (!data.HRP || !data.HRP.dates || data.HRP.dates.length === 0) {
                    document.getElementById('weightsChart').parentElement.innerHTML = '<p>Weights data not available</p>';
                    return;
                }

                const ctx = document.getElementById('weightsChart').getContext('2d');

                if (charts.weights) charts.weights.destroy();

                // Extract symbols (skip dates)
                const symbols = Object.keys(data.HRP).filter(k => k !== 'dates');
                const colors = ['#667eea', '#764ba2', '#f59e0b', '#ec4899'];

                const datasets = symbols.map((symbol, idx) => ({
                    label: symbol,
                    data: data.HRP[symbol] || [],
                    backgroundColor: colors[idx % colors.length],
                    borderColor: colors[idx % colors.length],
                    pointRadius: 0,
                    borderWidth: 0,
                    fill: true,
                    tension: 0.2
                }));

                if (datasets.length === 0) {
                    document.getElementById('weightsChart').parentElement.innerHTML = '<p>No weights data available</p>';
                    return;
                }

                charts.weights = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: data.HRP.dates,
                        datasets: datasets
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                stacked: true,
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

            function displayTransactions(data) {
                // HRP Transactions
                const hrpBody = document.getElementById('hrpTransactionsBody');
                hrpBody.innerHTML = '';
                if (data.HRP && data.HRP.length > 0) {
                    data.HRP.forEach(tx => {
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
                        hrpBody.appendChild(row);
                    });
                } else {
                    hrpBody.innerHTML = '<tr><td colspan="6">No transactions</td></tr>';
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


@app.route("/api/data")
def api_data():
    """API endpoint to serve all dashboard data as JSON."""
    try:
        results = load_results()

        # Debug: Log what was loaded
        print(f"Loaded results keys: {list(results.keys())}")

        if not results:
            return jsonify({"error": "No backtest results found. Run the backtest first: python scripts/run_hrp_backtest.py"}), 400

        return jsonify(
            {
                "metrics": get_metrics_table(results),
                "portfolio_value": get_portfolio_value_data(results),
                "drawdown": get_drawdown_data(results),
                "weights": get_weights_data(results),
                "transactions": get_transactions_data(results),
            }
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Error loading data: {str(e)}"}), 500


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("HRP Backtest Dashboard")
    print("=" * 60)
    print("\n[*] Starting server...\n")
    print("[*] Open your browser and navigate to: http://localhost:5000\n")
    print("Press Ctrl+C to stop the server\n")
    print("=" * 60 + "\n")

    app.run(debug=True, port=5000)
