#!/usr/bin/env python3
"""
Interactive web dashboard for portfolio strategy backtest results.

Supports:
1. Running from all-strategies backtest (with strategy picker)
2. Single strategy vs benchmark comparison (legacy mode)
3. Dynamic strategy selection and comparison

Run with: python scripts/serve_results.py
Then visit: http://localhost:5000
"""

import csv
import io
import json
import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from flask import Flask, Response, jsonify, render_template_string, request

# Configuration
BASE_DIR = Path(__file__).parent.parent
RESULTS_DIR = BASE_DIR / "results"

app = Flask(__name__, static_folder=None)

# Global data (loaded at startup)
STRATEGIES_INDEX = None
AVAILABLE_STRATEGIES = {}


def load_strategies_index():
    """
    Load the strategies index from all-strategies run.

    Returns dict with available strategies and their paths.
    Falls back to legacy metadata.json if index doesn't exist.
    """
    index_path = RESULTS_DIR / 'strategies_index.json'

    if index_path.exists():
        try:
            with open(index_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"   [!] Error loading strategies_index.json: {e}")

    # Fallback to legacy metadata.json for backward compatibility
    metadata_path = RESULTS_DIR / 'metadata.json'
    if metadata_path.exists():
        try:
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
                # Convert legacy format to index format
                return {
                    'run_date': datetime.now().isoformat(),
                    'total_strategies': 2,
                    'strategies': {},
                    'config': metadata.get('config', {})
                }
        except Exception as e:
            print(f"   [!] Error loading metadata.json: {e}")

    return None


def load_strategy_data(strategy_key: str) -> dict:
    """
    Load all data for a specific strategy from its folder.

    Args:
        strategy_key: Strategy identifier (e.g., 'hrp_single')

    Returns:
        Dict with portfolio_history, transactions, weights_history, metrics, info
    """
    strategy_dir = RESULTS_DIR / 'strategies' / strategy_key

    if not strategy_dir.exists():
        return None

    data = {
        'key': strategy_key,
        'portfolio_history': [],
        'transactions': [],
        'weights_history': [],
        'metrics': {},
        'info': {}
    }

    # Load portfolio history
    portfolio_path = strategy_dir / 'portfolio_history.json'
    if portfolio_path.exists():
        with open(portfolio_path, 'r') as f:
            data['portfolio_history'] = json.load(f)

    # Load transactions
    transactions_path = strategy_dir / 'transactions.json'
    if transactions_path.exists():
        with open(transactions_path, 'r') as f:
            data['transactions'] = json.load(f)

    # Load weights history
    weights_path = strategy_dir / 'weights_history.json'
    if weights_path.exists():
        with open(weights_path, 'r') as f:
            data['weights_history'] = json.load(f)

    # Load metrics
    metrics_path = strategy_dir / 'metrics.json'
    if metrics_path.exists():
        with open(metrics_path, 'r') as f:
            data['metrics'] = json.load(f)

    # Load info
    info_path = strategy_dir / 'info.json'
    if info_path.exists():
        with open(info_path, 'r') as f:
            data['info'] = json.load(f)

    return data


def get_portfolio_value_data(strategy_data: dict, strategy_name: str = None) -> dict:
    """Extract portfolio value time series from strategy data."""
    if not strategy_data or not strategy_data.get('portfolio_history'):
        return {}

    name = strategy_name or strategy_data.get('key', 'Strategy')
    df_dict = pd.DataFrame(strategy_data['portfolio_history']).to_dict()

    return {
        name: {
            'dates': [entry.get('date', entry.get('timestamp', '')) for entry in strategy_data['portfolio_history']],
            'values': [entry.get('total_value', 0) for entry in strategy_data['portfolio_history']]
        }
    }


def get_drawdown_data(strategy_data: dict, strategy_name: str = None) -> dict:
    """Calculate drawdown from portfolio history."""
    if not strategy_data or not strategy_data.get('portfolio_history'):
        return {}

    name = strategy_name or strategy_data.get('key', 'Strategy')
    portfolio = strategy_data['portfolio_history']

    if not portfolio:
        return {}

    values = [entry.get('total_value', 0) for entry in portfolio]
    dates = [entry.get('date', entry.get('timestamp', '')) for entry in portfolio]

    if not values:
        return {}

    # Calculate drawdown
    values_array = np.array(values)
    running_max = np.maximum.accumulate(values_array)
    drawdown = ((values_array - running_max) / running_max) * 100

    return {
        name: {
            'dates': dates,
            'drawdown': drawdown.tolist()
        }
    }


def get_weights_data(strategy_data: dict, strategy_name: str = None) -> dict:
    """Extract portfolio weights over time."""
    if not strategy_data or not strategy_data.get('weights_history'):
        return {}

    name = strategy_name or strategy_data.get('key', 'Strategy')

    weights_list = strategy_data['weights_history']
    if not weights_list:
        return {}

    # Convert to format expected by frontend
    weights_data = {
        'dates': [entry.get('date', entry.get('timestamp', '')) for entry in weights_list]
    }

    # Extract all symbols from first entry
    first_entry = weights_list[0] if weights_list else {}
    symbols = [k for k in first_entry.keys() if k not in ['date', 'timestamp']]

    # Add symbol data
    for symbol in symbols:
        weights_data[symbol] = [entry.get(symbol, 0) for entry in weights_list]

    return {name: weights_data}


def get_transactions_data(strategy_data: dict, strategy_name: str = None) -> dict:
    """Extract transaction data."""
    if not strategy_data or not strategy_data.get('transactions'):
        return {}

    name = strategy_name or strategy_data.get('key', 'Strategy')
    return {name: strategy_data['transactions']}


@app.route("/")
def index():
    """Serve the main dashboard page."""
    # Check if we have all-strategies results
    has_all_strategies = (RESULTS_DIR / 'strategies_index.json').exists()

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

            .controls {
                background: #f5f5f5;
                padding: 20px 30px;
                border-bottom: 2px solid #e0e0e0;
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px;
                align-items: center;
            }

            .control-group {
                display: flex;
                flex-direction: column;
                gap: 5px;
            }

            .control-group label {
                font-weight: 600;
                color: #333;
                font-size: 0.9em;
            }

            .control-group select {
                padding: 10px;
                border: 2px solid #ddd;
                border-radius: 6px;
                font-size: 1em;
                background: white;
                cursor: pointer;
                transition: border-color 0.3s;
            }

            .control-group select:focus {
                outline: none;
                border-color: #667eea;
            }

            .view-mode-buttons {
                display: flex;
                gap: 10px;
                justify-content: center;
                grid-column: 1 / -1;
            }

            .view-mode-btn {
                padding: 10px 20px;
                border: 2px solid #667eea;
                background: white;
                color: #667eea;
                border-radius: 6px;
                cursor: pointer;
                font-weight: 600;
                transition: all 0.3s ease;
            }

            .view-mode-btn.active {
                background: #667eea;
                color: white;
            }

            .view-mode-btn:hover {
                background: #f0f4ff;
            }

            .view-mode-btn.active:hover {
                background: #667eea;
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

                .controls {
                    grid-template-columns: 1fr;
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

            <div class="controls" id="controls">
                <div class="control-group">
                    <label for="strategySelect">Strategy 1:</label>
                    <select id="strategySelect" onchange="handleStrategyChange()">
                        <option value="">Loading...</option>
                    </select>
                </div>
                <div class="control-group" id="strategy2Container" style="display: none;">
                    <label for="strategy2Select">Strategy 2 (Comparison):</label>
                    <select id="strategy2Select" onchange="handleStrategyChange()">
                        <option value="">None (View single strategy)</option>
                    </select>
                </div>
                <div class="view-mode-buttons">
                    <button class="view-mode-btn active" onclick="setViewMode('single')">Single View</button>
                    <button class="view-mode-btn" onclick="setViewMode('comparison')">Comparison</button>
                </div>
            </div>

            <div class="tabs">
                <button class="tab-button active" onclick="showTab('overview')">Overview</button>
                <button class="tab-button" onclick="showTab('portfolio')">Portfolio Value</button>
                <button class="tab-button" onclick="showTab('drawdown')">Drawdown</button>
                <button class="tab-button" onclick="showTab('weights')">Weights</button>
                <button class="tab-button" onclick="showTab('monthly')">Monthly Returns</button>
                <button class="tab-button" onclick="showTab('rolling')">Rolling Metrics</button>
                <button class="tab-button" onclick="showTab('transactions')">Transactions</button>
            </div>

            <div class="content">
                <!-- Overview Tab -->
                <div id="overview" class="tab-panel active">
                    <h2>Performance Metrics</h2>
                    <table class="metrics-table" id="metricsTable">
                        <thead>
                            <tr id="metricsHeaderRow">
                                <th>Metric</th>
                                <th id="headerCol1">Strategy</th>
                            </tr>
                        </thead>
                        <tbody id="metricsBody">
                            <tr><td colspan="3" class="loading">Loading...</td></tr>
                        </tbody>
                    </table>

                    <h2 style="margin-top: 40px;">Key Metrics</h2>
                    <div class="metrics-grid" id="metricsGrid"></div>
                </div>

                <!-- Portfolio Value Tab -->
                <div id="portfolio" class="tab-panel">
                    <h2 style="display: flex; justify-content: space-between; align-items: center;">Portfolio Value Over Time <button class="view-mode-btn" onclick="exportCSV('portfolio')" style="font-size: 0.7em; padding: 6px 12px;">Export CSV</button></h2>
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
                    <h2>Portfolio Weights Over Time</h2>
                    <div class="chart-container">
                        <canvas id="weightsChart"></canvas>
                    </div>
                </div>

                <!-- Monthly Returns Tab -->
                <div id="monthly" class="tab-panel">
                    <h2>Monthly Returns Heatmap</h2>
                    <div id="monthlyHeatmap" style="overflow-x: auto;"></div>
                </div>

                <!-- Rolling Metrics Tab -->
                <div id="rolling" class="tab-panel">
                    <h2>Rolling Metrics</h2>
                    <div style="margin-bottom: 15px; display: flex; gap: 10px; align-items: center;">
                        <label for="rollingMetricSelect" style="font-weight: 600;">Metric:</label>
                        <select id="rollingMetricSelect" onchange="loadRollingMetrics()" style="padding: 8px; border-radius: 6px; border: 2px solid #ddd;">
                            <option value="sharpe">Sharpe Ratio</option>
                            <option value="volatility">Volatility</option>
                            <option value="sortino">Sortino Ratio</option>
                        </select>
                        <label for="rollingWindowSelect" style="font-weight: 600; margin-left: 10px;">Window:</label>
                        <select id="rollingWindowSelect" onchange="loadRollingMetrics()" style="padding: 8px; border-radius: 6px; border: 2px solid #ddd;">
                            <option value="21">21d (~1 month)</option>
                            <option value="63" selected>63d (~3 months)</option>
                            <option value="126">126d (~6 months)</option>
                            <option value="252">252d (~1 year)</option>
                        </select>
                    </div>
                    <div class="chart-container">
                        <canvas id="rollingChart"></canvas>
                    </div>
                </div>

                <!-- Transactions Tab -->
                <div id="transactions" class="tab-panel">
                    <h2 style="display: flex; justify-content: space-between; align-items: center;">Transaction History <button class="view-mode-btn" onclick="exportCSV('transactions')" style="font-size: 0.7em; padding: 6px 12px;">Export CSV</button></h2>
                    <table class="transactions-table" id="transactionsTable">
                        <thead>
                            <tr>
                                <th>Date</th>
                                <th>Symbol</th>
                                <th>Quantity</th>
                                <th>Price</th>
                                <th>Cost</th>
                            </tr>
                        </thead>
                        <tbody id="transactionsBody">
                            <tr><td colspan="5">No transactions</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <script>
            let charts = {};
            let currentViewMode = 'single';
            let availableStrategies = [];
            let loadedData = {};

            // Format currency values with £ and comma separators
            function formatCurrency(value) {
                if (value === null || value === undefined) return '—';
                const num = parseFloat(value);
                if (isNaN(num)) return '—';
                return '£' + num.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            }

            // Format metric values with appropriate formatting based on type
            function formatMetric(key, value) {
                if (value === null || value === undefined) return '—';

                // Currency-related metrics
                if (key.toLowerCase().includes('value') || key.toLowerCase().includes('cost') ||
                    key.toLowerCase().includes('capital') || key.toLowerCase() === 'final_value') {
                    return formatCurrency(value);
                }

                // Percentage-related metrics (displayed as percentage)
                if (key.toLowerCase().includes('return') || key.toLowerCase().includes('volatility') ||
                    key.toLowerCase().includes('drawdown') || key.toLowerCase().includes('sharpe')) {
                    const num = parseFloat(value);
                    if (isNaN(num)) return value;

                    // If it's a ratio (between -1 and 1, excluding sharpe), multiply by 100
                    if ((key.toLowerCase().includes('return') ||
                         key.toLowerCase().includes('volatility') ||
                         key.toLowerCase().includes('drawdown')) &&
                        num >= -1 && num <= 1) {
                        return (num * 100).toFixed(2) + '%';
                    }
                    // For sharpe ratio and similar, just show decimal
                    return num.toFixed(2);
                }

                // Transaction count metrics
                if (key.toLowerCase().includes('transaction') || key.toLowerCase().includes('rebalance') ||
                    key.toLowerCase().includes('count')) {
                    return Math.round(parseFloat(value));
                }

                // Default formatting
                const num = parseFloat(value);
                return isNaN(num) ? value : num.toFixed(2);
            }

            async function initializeDashboard() {
                try {
                    // Get available strategies
                    const response = await fetch('/api/strategies');
                    availableStrategies = await response.json();

                    // Populate dropdowns
                    const select1 = document.getElementById('strategySelect');
                    const select2 = document.getElementById('strategy2Select');

                    const optionsHtml = availableStrategies.map(s =>
                        `<option value="${s}">${s}</option>`
                    ).join('');

                    select1.innerHTML = optionsHtml;
                    select2.innerHTML = '<option value="">None (View single strategy)</option>' + optionsHtml;

                    // Show strategy 2 selector if we have multiple strategies
                    if (availableStrategies.length > 1) {
                        document.getElementById('strategy2Container').style.display = 'block';
                    }

                    // Load first strategy
                    if (availableStrategies.length > 0) {
                        await handleStrategyChange();
                    }
                } catch (error) {
                    console.error('Error initializing dashboard:', error);
                    document.querySelector('.content').innerHTML =
                        '<div class="error">Error loading strategies. Make sure to run: python scripts/run_backtest.py --all</div>';
                }
            }

            async function handleStrategyChange() {
                const strategy1 = document.getElementById('strategySelect').value;
                const strategy2 = document.getElementById('strategy2Select').value;

                if (!strategy1) return;

                // Load strategy data
                if (!loadedData[strategy1]) {
                    await loadStrategyData(strategy1);
                }
                if (strategy2 && !loadedData[strategy2]) {
                    await loadStrategyData(strategy2);
                }

                // Update dashboard
                updateDashboard(strategy1, strategy2);
            }

            async function loadStrategyData(strategyKey) {
                try {
                    const response = await fetch(`/api/strategy/${strategyKey}`);
                    const data = await response.json();
                    loadedData[strategyKey] = data;
                } catch (error) {
                    console.error(`Error loading strategy ${strategyKey}:`, error);
                }
            }

            function updateDashboard(strategy1, strategy2) {
                const data1 = loadedData[strategy1];
                if (!data1) return;

                const data2 = strategy2 ? loadedData[strategy2] : null;

                // Update metrics table header
                const headerRow = document.getElementById('metricsHeaderRow');
                if (data2) {
                    headerRow.innerHTML = `<th>Metric</th><th>${strategy1}</th><th>${strategy2}</th>`;
                } else {
                    headerRow.innerHTML = `<th>Metric</th><th>${strategy1}</th>`;
                }

                // Update content
                displayMetrics(data1, data2, strategy1, strategy2);
                displayPortfolioChart(data1, data2, strategy1, strategy2);
                displayDrawdownChart(data1, data2, strategy1, strategy2);
                displayWeightsChart(data1, data2, strategy1, strategy2);
                displayTransactions(data1);
                loadMonthlyReturns(strategy1);
            }

            function displayMetrics(data1, data2, name1, name2) {
                const tbody = document.getElementById('metricsBody');
                tbody.innerHTML = '';

                const metrics1 = data1.metrics || {};
                const metrics2 = data2 ? (data2.metrics || {}) : null;

                const metricKeys = Object.keys(metrics1);
                for (const key of metricKeys) {
                    const row = document.createElement('tr');
                    const value1 = formatMetric(key, metrics1[key]);
                    let html = `<td><strong>${key}</strong></td><td>${value1}</td>`;
                    if (metrics2) {
                        const value2 = formatMetric(key, metrics2[key]);
                        html += `<td>${value2}</td>`;
                    }
                    row.innerHTML = html;
                    tbody.appendChild(row);
                }
            }

            function displayPortfolioChart(data1, data2, name1, name2) {
                const ctx = document.getElementById('portfolioChart').getContext('2d');
                if (charts.portfolio) charts.portfolio.destroy();

                const portfolioData1 = data1.portfolio_history || [];
                const dates = portfolioData1.map(p => p.date || p.timestamp).slice(0, 100); // Limit points for performance
                const values1 = portfolioData1.map(p => p.total_value).slice(0, 100);

                const datasets = [{
                    label: name1,
                    data: values1,
                    borderColor: '#667eea',
                    backgroundColor: 'rgba(102, 126, 234, 0.1)',
                    tension: 0.4,
                    pointRadius: 0,
                    borderWidth: 2,
                }];

                if (data2) {
                    const portfolioData2 = data2.portfolio_history || [];
                    const values2 = portfolioData2.map(p => p.total_value).slice(0, 100);
                    datasets.push({
                        label: name2,
                        data: values2,
                        borderColor: '#f59e0b',
                        backgroundColor: 'rgba(245, 158, 11, 0.1)',
                        tension: 0.4,
                        pointRadius: 0,
                        borderWidth: 2,
                    });
                }

                charts.portfolio = new Chart(ctx, {
                    type: 'line',
                    data: { labels: dates, datasets: datasets },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { display: true, position: 'top' },
                            tooltip: {
                                callbacks: {
                                    label: function(context) {
                                        return context.dataset.label + ': ' + formatCurrency(context.parsed.y);
                                    }
                                }
                            }
                        },
                        scales: {
                            y: {
                                beginAtZero: false,
                                ticks: { callback: v => formatCurrency(v) }
                            }
                        }
                    }
                });
            }

            function displayDrawdownChart(data1, data2, name1, name2) {
                const ctx = document.getElementById('drawdownChart').getContext('2d');
                if (charts.drawdown) charts.drawdown.destroy();

                const portfolio1 = (data1.portfolio_history || []).slice(0, 100);
                const dates = portfolio1.map(p => p.date || p.timestamp);

                // Calculate drawdown
                const values1 = portfolio1.map(p => p.total_value);
                const runningMax1 = values1.reduce((acc, val) => {
                    acc.push(acc.length === 0 ? val : Math.max(acc[acc.length - 1], val));
                    return acc;
                }, []);
                const drawdown1 = values1.map((val, i) => ((val - runningMax1[i]) / runningMax1[i]) * 100);

                const datasets = [{
                    label: name1,
                    data: drawdown1,
                    borderColor: '#667eea',
                    backgroundColor: 'rgba(102, 126, 234, 0.2)',
                    tension: 0.4,
                    pointRadius: 0,
                    borderWidth: 2,
                    fill: true,
                }];

                if (data2) {
                    const portfolio2 = (data2.portfolio_history || []).slice(0, 100);
                    const values2 = portfolio2.map(p => p.total_value);
                    const runningMax2 = values2.reduce((acc, val) => {
                        acc.push(acc.length === 0 ? val : Math.max(acc[acc.length - 1], val));
                        return acc;
                    }, []);
                    const drawdown2 = values2.map((val, i) => ((val - runningMax2[i]) / runningMax2[i]) * 100);

                    datasets.push({
                        label: name2,
                        data: drawdown2,
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
                    data: { labels: dates, datasets: datasets },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: { y: { max: 0, ticks: { callback: v => v + '%' } } },
                        plugins: { legend: { display: true, position: 'top' } }
                    }
                });
            }

            function displayWeightsChart(data1, data2, name1, name2) {
                const weightsData = (data1 && data1.weights_history) || [];
                if (!weightsData || weightsData.length === 0) {
                    document.getElementById('weightsChart').parentElement.innerHTML = '<p>Weights data not available</p>';
                    return;
                }

                const ctx = document.getElementById('weightsChart').getContext('2d');
                if (charts.weights) charts.weights.destroy();

                const dates = weightsData.map(w => w.date || w.timestamp).slice(0, 100);
                const firstEntry = weightsData[0] || {};
                const symbols = Object.keys(firstEntry).filter(k => k !== 'date' && k !== 'timestamp');
                const colors = ['#667eea', '#764ba2', '#f59e0b', '#ec4899', '#10b981', '#f97316'];

                const datasets = symbols.map((symbol, idx) => {
                    const values = weightsData.map(w => {
                        const val = w[symbol] || 0;
                        // Convert decimal to percentage if needed (0.5 -> 50)
                        return val > 1 ? val : val * 100;
                    }).slice(0, 100);

                    return {
                        label: symbol,
                        data: values,
                        backgroundColor: colors[idx % colors.length],
                        borderColor: colors[idx % colors.length],
                        pointRadius: 0,
                        borderWidth: 1,
                        fill: true,
                        tension: 0.3,
                        segment: {
                            borderDash: []
                        }
                    };
                });

                charts.weights = new Chart(ctx, {
                    type: 'line',
                    data: { labels: dates, datasets: datasets },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                stacked: true,
                                beginAtZero: true,
                                min: 0,
                                max: 100,
                                ticks: { callback: v => v.toFixed(0) + '%' }
                            }
                        },
                        plugins: {
                            filler: { propagate: true },
                            legend: { display: true, position: 'top' }
                        }
                    }
                });
            }

            function displayTransactions(data) {
                const tbody = document.getElementById('transactionsBody');
                tbody.innerHTML = '';

                const transactions = data.transactions || [];
                if (transactions.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="5">No transactions</td></tr>';
                    return;
                }

                transactions.slice(0, 50).forEach(tx => {
                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td>${tx.date || tx.timestamp}</td>
                        <td>${tx.symbol}</td>
                        <td>${tx.quantity}</td>
                        <td>${formatCurrency(tx.price)}</td>
                        <td>${formatCurrency(tx.cost)}</td>
                    `;
                    tbody.appendChild(row);
                });
            }

            function showTab(tabName) {
                document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
                document.querySelectorAll('.tab-button').forEach(b => b.classList.remove('active'));
                document.getElementById(tabName).classList.add('active');
                event.target.classList.add('active');
            }

            function setViewMode(mode) {
                currentViewMode = mode;
                const buttons = document.querySelectorAll('.view-mode-btn');
                buttons.forEach(b => b.classList.remove('active'));
                event.target.classList.add('active');

                if (mode === 'comparison') {
                    document.getElementById('strategy2Container').style.display = 'block';
                } else {
                    document.getElementById('strategy2Select').value = '';
                }
                handleStrategyChange();
            }

            async function loadMonthlyReturns(strategyKey) {
                try {
                    const response = await fetch(`/api/strategy/${strategyKey}/monthly_returns`);
                    const data = await response.json();

                    const container = document.getElementById('monthlyHeatmap');
                    if (!data || data.length === 0) {
                        container.innerHTML = '<p>No monthly returns data available</p>';
                        return;
                    }

                    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                                    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
                    const years = [...new Set(data.map(d => d.year))].sort();

                    let html = '<table class="metrics-table"><thead><tr><th>Year</th>';
                    months.forEach(m => html += `<th>${m}</th>`);
                    html += '<th>Annual</th></tr></thead><tbody>';

                    for (const year of years) {
                        html += `<tr><td><strong>${year}</strong></td>`;
                        let yearReturn = 1;
                        for (let m = 1; m <= 12; m++) {
                            const entry = data.find(d => d.year === year && d.month === m);
                            if (entry) {
                                const val = entry.return;
                                yearReturn *= (1 + val / 100);
                                const color = val >= 0 ? `rgba(40,167,69,${Math.min(Math.abs(val)/5, 0.8)})` :
                                                         `rgba(220,53,69,${Math.min(Math.abs(val)/5, 0.8)})`;
                                html += `<td style="background:${color}; text-align:center; font-weight:600;">${val.toFixed(1)}%</td>`;
                            } else {
                                html += '<td style="text-align:center; color:#ccc;">-</td>';
                            }
                        }
                        const annualReturn = (yearReturn - 1) * 100;
                        const annualColor = annualReturn >= 0 ? '#28a745' : '#dc3545';
                        html += `<td style="text-align:center; font-weight:700; color:${annualColor};">${annualReturn.toFixed(1)}%</td>`;
                        html += '</tr>';
                    }
                    html += '</tbody></table>';
                    container.innerHTML = html;
                } catch (error) {
                    console.error('Error loading monthly returns:', error);
                    document.getElementById('monthlyHeatmap').innerHTML = '<p>Error loading monthly returns</p>';
                }
            }

            async function loadRollingMetrics() {
                const strategy1 = document.getElementById('strategySelect').value;
                if (!strategy1) return;

                const metric = document.getElementById('rollingMetricSelect').value;
                const window = document.getElementById('rollingWindowSelect').value;

                try {
                    const response = await fetch(`/api/strategy/${strategy1}/rolling?metric=${metric}&window=${window}`);
                    const result = await response.json();

                    if (result.error) {
                        console.error(result.error);
                        return;
                    }

                    const ctx = document.getElementById('rollingChart').getContext('2d');
                    if (charts.rolling) charts.rolling.destroy();

                    const dates = result.data.map(d => d.date);
                    const values = result.data.map(d => d.value);

                    const metricLabels = {sharpe: 'Sharpe Ratio', volatility: 'Volatility (%)', sortino: 'Sortino Ratio'};

                    const datasets = [{
                        label: `Rolling ${metricLabels[metric]} (${window}d) - ${strategy1}`,
                        data: values,
                        borderColor: '#667eea',
                        backgroundColor: 'rgba(102, 126, 234, 0.1)',
                        tension: 0.4,
                        pointRadius: 0,
                        borderWidth: 2,
                        fill: true,
                    }];

                    // Load second strategy if in comparison mode
                    const strategy2 = document.getElementById('strategy2Select').value;
                    if (strategy2) {
                        const response2 = await fetch(`/api/strategy/${strategy2}/rolling?metric=${metric}&window=${window}`);
                        const result2 = await response2.json();
                        if (!result2.error) {
                            datasets.push({
                                label: `Rolling ${metricLabels[metric]} (${window}d) - ${strategy2}`,
                                data: result2.data.map(d => d.value),
                                borderColor: '#f59e0b',
                                backgroundColor: 'rgba(245, 158, 11, 0.1)',
                                tension: 0.4,
                                pointRadius: 0,
                                borderWidth: 2,
                                fill: true,
                            });
                        }
                    }

                    charts.rolling = new Chart(ctx, {
                        type: 'line',
                        data: { labels: dates, datasets: datasets },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: { legend: { display: true, position: 'top' } },
                            scales: {
                                y: {
                                    ticks: {
                                        callback: v => metric === 'volatility' ? v.toFixed(1) + '%' : v.toFixed(2)
                                    }
                                }
                            }
                        }
                    });
                } catch (error) {
                    console.error('Error loading rolling metrics:', error);
                }
            }

            function exportCSV(type) {
                const strategy = document.getElementById('strategySelect').value;
                if (!strategy) return;
                window.open(`/api/strategy/${strategy}/export?type=${type}`, '_blank');
            }

            // Initialize on page load
            document.addEventListener('DOMContentLoaded', initializeDashboard);
        </script>
    </body>
    </html>
    """

    return render_template_string(html)


@app.route("/api/strategies")
def api_strategies():
    """API endpoint to get list of available strategies."""
    global STRATEGIES_INDEX

    if STRATEGIES_INDEX is None:
        STRATEGIES_INDEX = load_strategies_index()

    if STRATEGIES_INDEX and 'strategies' in STRATEGIES_INDEX:
        return jsonify(list(STRATEGIES_INDEX['strategies'].keys()))

    # Fallback: check for strategy folders
    strategies_dir = RESULTS_DIR / 'strategies'
    if strategies_dir.exists():
        strategies = [d.name for d in strategies_dir.iterdir() if d.is_dir()]
        return jsonify(sorted(strategies))

    return jsonify([])


@app.route("/api/strategy/<strategy_key>")
def api_strategy(strategy_key: str):
    """API endpoint to get data for a specific strategy."""
    data = load_strategy_data(strategy_key)

    if not data:
        return jsonify({"error": f"Strategy {strategy_key} not found"}), 404

    return jsonify(data)


@app.route("/api/strategy/<strategy_key>/monthly_returns")
def api_monthly_returns(strategy_key: str):
    """API endpoint for monthly returns heatmap data."""
    data = load_strategy_data(strategy_key)
    if not data:
        return jsonify({"error": f"Strategy {strategy_key} not found"}), 404

    portfolio = data.get('portfolio_history', [])
    if not portfolio:
        return jsonify({"error": "No portfolio history"}), 404

    values = pd.Series(
        [p['total_value'] for p in portfolio],
        index=pd.to_datetime([p.get('date', p.get('timestamp')) for p in portfolio])
    )

    monthly = values.resample('ME').last()
    monthly_returns = monthly.pct_change().dropna()

    result = []
    for date, ret in monthly_returns.items():
        result.append({
            'year': int(date.year),
            'month': int(date.month),
            'return': round(float(ret) * 100, 2)
        })

    return jsonify(result)


@app.route("/api/strategy/<strategy_key>/rolling")
def api_rolling_metrics(strategy_key: str):
    """API endpoint for rolling metrics data."""
    data = load_strategy_data(strategy_key)
    if not data:
        return jsonify({"error": f"Strategy {strategy_key} not found"}), 404

    metric = request.args.get('metric', 'sharpe')
    window = int(request.args.get('window', 63))

    portfolio = data.get('portfolio_history', [])
    if not portfolio:
        return jsonify({"error": "No portfolio history"}), 404

    values = pd.Series(
        [p['total_value'] for p in portfolio],
        index=pd.to_datetime([p.get('date', p.get('timestamp')) for p in portfolio])
    )
    returns = values.pct_change().dropna()

    if len(returns) < window:
        return jsonify({"error": f"Insufficient data for window={window}"}), 400

    results = []
    for i in range(window, len(returns) + 1):
        window_returns = returns.iloc[i - window:i]
        date = returns.index[i - 1]

        if metric == 'sharpe':
            mean_r = window_returns.mean()
            std_r = window_returns.std()
            val = (mean_r / std_r * np.sqrt(252)) if std_r > 0 else 0
        elif metric == 'volatility':
            val = window_returns.std() * np.sqrt(252) * 100
        elif metric == 'sortino':
            downside = window_returns[window_returns < 0]
            down_std = np.sqrt((downside ** 2).mean()) if len(downside) > 0 else 0
            val = (window_returns.mean() / down_std * np.sqrt(252)) if down_std > 0 else 0
        else:
            val = 0

        results.append({
            'date': date.isoformat(),
            'value': round(float(val), 4)
        })

    return jsonify({'metric': metric, 'window': window, 'data': results})


@app.route("/api/strategy/<strategy_key>/export")
def api_export(strategy_key: str):
    """Export strategy data as CSV."""
    data = load_strategy_data(strategy_key)
    if not data:
        return jsonify({"error": f"Strategy {strategy_key} not found"}), 404

    export_type = request.args.get('type', 'portfolio')

    if export_type == 'portfolio':
        rows = data.get('portfolio_history', [])
    elif export_type == 'transactions':
        rows = data.get('transactions', [])
    elif export_type == 'weights':
        rows = data.get('weights_history', [])
    else:
        return jsonify({"error": f"Unknown export type: {export_type}"}), 400

    if not rows:
        return jsonify({"error": "No data to export"}), 404

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={strategy_key}_{export_type}.csv'}
    )


@app.route("/api/compare/<key1>/<key2>")
def api_compare(key1: str, key2: str):
    """API endpoint for comparison metrics between two strategies."""
    data1 = load_strategy_data(key1)
    data2 = load_strategy_data(key2)

    if not data1 or not data2:
        return jsonify({"error": "One or both strategies not found"}), 404

    portfolio1 = data1.get('portfolio_history', [])
    portfolio2 = data2.get('portfolio_history', [])

    if not portfolio1 or not portfolio2:
        return jsonify({"error": "Missing portfolio history"}), 404

    values1 = pd.Series(
        [p['total_value'] for p in portfolio1],
        index=pd.to_datetime([p.get('date', p.get('timestamp')) for p in portfolio1])
    )
    values2 = pd.Series(
        [p['total_value'] for p in portfolio2],
        index=pd.to_datetime([p.get('date', p.get('timestamp')) for p in portfolio2])
    )

    # Align on common dates
    common = values1.index.intersection(values2.index)
    if len(common) < 2:
        return jsonify({"error": "Insufficient overlapping data"}), 400

    returns1 = values1[common].pct_change().dropna()
    returns2 = values2[common].pct_change().dropna()

    active_returns = returns1 - returns2
    tracking_error = float(active_returns.std() * np.sqrt(252))
    info_ratio = float(active_returns.mean() / active_returns.std() * np.sqrt(252)) if active_returns.std() > 0 else 0

    # Relative performance (strategy1 / strategy2)
    relative = (values1[common] / values2[common]).dropna()
    relative_data = [
        {'date': d.isoformat(), 'value': round(float(v), 4)}
        for d, v in relative.items()
    ]

    return jsonify({
        'tracking_error': round(tracking_error * 100, 2),
        'information_ratio': round(info_ratio, 4),
        'relative_performance': relative_data
    })


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Strategy Backtest Dashboard")
    print("=" * 60)
    print("\n[*] Starting server...\n")
    print("[*] Open your browser and navigate to: http://localhost:5000\n")
    print("Press Ctrl+C to stop the server\n")
    print("=" * 60 + "\n")

    app.run(debug=True, port=5000)
