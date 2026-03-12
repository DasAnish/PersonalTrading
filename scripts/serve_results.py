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
                    <h2>Portfolio Weights Over Time</h2>
                    <div class="chart-container">
                        <canvas id="weightsChart"></canvas>
                    </div>
                </div>

                <!-- Transactions Tab -->
                <div id="transactions" class="tab-panel">
                    <h2>Transaction History</h2>
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
                displayWeightsChart(data1, strategy1);
                displayTransactions(data1);
            }

            function displayMetrics(data1, data2, name1, name2) {
                const tbody = document.getElementById('metricsBody');
                tbody.innerHTML = '';

                const metrics1 = data1.metrics || {};
                const metrics2 = data2 ? (data2.metrics || {}) : null;

                const metricKeys = Object.keys(metrics1);
                for (const key of metricKeys) {
                    const row = document.createElement('tr');
                    let html = `<td><strong>${key}</strong></td><td>${metrics1[key]}</td>`;
                    if (metrics2) {
                        html += `<td>${metrics2[key]}</td>`;
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
                        plugins: { legend: { display: true, position: 'top' } },
                        scales: { y: { beginAtZero: false } }
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

            function displayWeightsChart(data, name) {
                const weightsData = data.weights_history || [];
                if (!weightsData || weightsData.length === 0) {
                    document.getElementById('weightsChart').parentElement.innerHTML = '<p>Weights data not available</p>';
                    return;
                }

                const ctx = document.getElementById('weightsChart').getContext('2d');
                if (charts.weights) charts.weights.destroy();

                const dates = weightsData.map(w => w.date || w.timestamp);
                const firstEntry = weightsData[0] || {};
                const symbols = Object.keys(firstEntry).filter(k => k !== 'date' && k !== 'timestamp');
                const colors = ['#667eea', '#764ba2', '#f59e0b', '#ec4899'];

                const datasets = symbols.map((symbol, idx) => ({
                    label: symbol,
                    data: weightsData.map(w => w[symbol] || 0),
                    backgroundColor: colors[idx % colors.length],
                    borderColor: colors[idx % colors.length],
                    pointRadius: 0,
                    borderWidth: 0,
                    fill: true,
                    tension: 0.2
                }));

                charts.weights = new Chart(ctx, {
                    type: 'line',
                    data: { labels: dates, datasets: datasets },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                stacked: true,
                                max: 100,
                                ticks: { callback: v => v + '%' }
                            }
                        },
                        plugins: { legend: { display: true, position: 'top' } }
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
                        <td>£${parseFloat(tx.price).toFixed(2)}</td>
                        <td>£${parseFloat(tx.cost).toFixed(2)}</td>
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


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Strategy Backtest Dashboard")
    print("=" * 60)
    print("\n[*] Starting server...\n")
    print("[*] Open your browser and navigate to: http://localhost:5000\n")
    print("Press Ctrl+C to stop the server\n")
    print("=" * 60 + "\n")

    app.run(debug=True, port=5000)
