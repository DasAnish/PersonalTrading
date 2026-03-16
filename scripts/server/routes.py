"""Page routes for the dashboard server."""

from flask import Blueprint, render_template_string

bp = Blueprint("routes", __name__)

# ---------------------------------------------------------------------------
# Shared CSS
# ---------------------------------------------------------------------------

_SHARED_CSS = """
    * { margin: 0; padding: 0; box-sizing: border-box; }

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

    .header h1 { font-size: 2.5em; margin-bottom: 10px; }
    .header p { font-size: 1.1em; opacity: 0.9; }

    .content { padding: 30px; }

    .btn {
        padding: 10px 20px;
        border: 2px solid #667eea;
        background: white;
        color: #667eea;
        border-radius: 6px;
        cursor: pointer;
        font-weight: 600;
        text-decoration: none;
        display: inline-block;
        transition: all 0.3s ease;
    }

    .btn:hover { background: #f0f4ff; }
    .btn.primary { background: #667eea; color: white; }
    .btn.primary:hover { background: #5a6fd6; }

    .positive { color: #28a745; font-weight: 600; }
    .negative { color: #dc3545; font-weight: 600; }

    .loading { text-align: center; padding: 40px; color: #666; }
    .error {
        background: #fff3cd;
        color: #856404;
        padding: 20px;
        border-radius: 8px;
        margin-bottom: 20px;
    }

    @media (max-width: 768px) {
        .header h1 { font-size: 1.8em; }
    }
"""

# ---------------------------------------------------------------------------
# Overview page (/)
# ---------------------------------------------------------------------------

_OVERVIEW_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Strategy Backtest Dashboard</title>
    <style>
        %(shared_css)s

        .overview-table {
            width: 100%%;
            border-collapse: collapse;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            margin-top: 24px;
        }

        .overview-table thead { background: #667eea; color: white; }
        .overview-table th { padding: 14px 16px; text-align: left; font-weight: 600; }
        .overview-table td { padding: 12px 16px; border-bottom: 1px solid #e0e0e0; }
        .overview-table tbody tr:hover { background: #f5f7ff; cursor: pointer; }
        .overview-table tbody tr:last-child td { border-bottom: none; }

        .strategy-link { color: #667eea; font-weight: 600; text-decoration: none; }
        .strategy-link:hover { text-decoration: underline; }

        .sort-btn {
            background: none;
            border: none;
            color: white;
            cursor: pointer;
            font-weight: 600;
            font-size: 1em;
            padding: 0;
            display: flex;
            align-items: center;
            gap: 4px;
        }

        .sort-btn::after { content: '↕'; font-size: 0.8em; opacity: 0.7; }
        .sort-btn.asc::after { content: '↑'; opacity: 1; }
        .sort-btn.desc::after { content: '↓'; opacity: 1; }

        .th-wrap { display: flex; align-items: center; gap: 4px; }
        .metric-info {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 16px;
            height: 16px;
            border-radius: 50%%;
            background: rgba(255,255,255,0.25);
            color: white;
            font-size: 10px;
            font-weight: bold;
            cursor: help;
            position: relative;
            flex-shrink: 0;
        }
        .metric-info:hover::after {
            content: attr(data-tip);
            position: absolute;
            top: calc(100%% + 6px);
            left: 50%%;
            transform: translateX(-50%%);
            background: #1a1a2e;
            color: #fff;
            padding: 6px 10px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 400;
            white-space: nowrap;
            z-index: 100;
            pointer-events: none;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        }
        .metric-info:hover::before {
            content: '';
            position: absolute;
            top: calc(100%% + 2px);
            left: 50%%;
            transform: translateX(-50%%);
            border: 4px solid transparent;
            border-bottom-color: #1a1a2e;
            z-index: 100;
        }

        .summary-cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            margin-bottom: 8px;
        }

        .summary-card {
            background: linear-gradient(135deg, #667eea 0%%, #764ba2 100%%);
            color: white;
            padding: 18px 20px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }

        .summary-card h3 { font-size: 0.85em; opacity: 0.85; text-transform: uppercase; margin-bottom: 6px; }
        .summary-card .value { font-size: 1.8em; font-weight: bold; }
        .summary-card .sub { font-size: 0.8em; opacity: 0.8; margin-top: 2px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Strategy Backtest Dashboard</h1>
            <p>Overview of all backtested strategies</p>
        </div>

        <div class="content">
            <div class="summary-cards" id="summaryCards">
                <div class="summary-card">
                    <h3>Strategies</h3>
                    <div class="value" id="totalStrategies">—</div>
                </div>
                <div class="summary-card">
                    <h3>Best Sharpe</h3>
                    <div class="value" id="bestSharpe">—</div>
                    <div class="sub" id="bestSharpeName"></div>
                </div>
                <div class="summary-card">
                    <h3>Best CAGR</h3>
                    <div class="value" id="bestCagr">—</div>
                    <div class="sub" id="bestCagrName"></div>
                </div>
                <div class="summary-card">
                    <h3>Lowest Max DD</h3>
                    <div class="value" id="lowestDD">—</div>
                    <div class="sub" id="lowestDDName"></div>
                </div>
            </div>

            <table class="overview-table" id="overviewTable">
                <thead>
                    <tr>
                        <th><button class="sort-btn" onclick="sortTable('name')">Strategy</button></th>
                        <th><div class="th-wrap"><button class="sort-btn" onclick="sortTable('sharpe_ratio')">Sharpe Ratio</button><span class="metric-info" data-tip="Risk-adjusted return: annualised mean return ÷ annualised std dev. Higher is better.">i</span></div></th>
                        <th><div class="th-wrap"><button class="sort-btn" onclick="sortTable('cagr')">CAGR</button><span class="metric-info" data-tip="Compound Annual Growth Rate: the geometric average annual return over the full period.">i</span></div></th>
                        <th><div class="th-wrap"><button class="sort-btn" onclick="sortTable('max_drawdown')">Max Drawdown</button><span class="metric-info" data-tip="Largest peak-to-trough decline in portfolio value. Less negative is better.">i</span></div></th>
                        <th><div class="th-wrap"><button class="sort-btn" onclick="sortTable('volatility')">Volatility</button><span class="metric-info" data-tip="Annualised standard deviation of daily returns. Lower means smoother equity curve.">i</span></div></th>
                        <th><div class="th-wrap"><button class="sort-btn" onclick="sortTable('total_return')">Total Return</button><span class="metric-info" data-tip="Cumulative percentage gain from start to end of the backtest period.">i</span></div></th>
                        <th><div class="th-wrap"><button class="sort-btn" onclick="sortTable('calmar_ratio')">Calmar</button><span class="metric-info" data-tip="CAGR ÷ |Max Drawdown|. Measures return earned per unit of drawdown risk. Higher is better.">i</span></div></th>
                        <th><div class="th-wrap"><button class="sort-btn" onclick="sortTable('omega_ratio')">Omega</button><span class="metric-info" data-tip="Sum of gains above 0 ÷ sum of losses below 0. Values &gt; 1 indicate more gains than losses. Higher is better.">i</span></div></th>
                    </tr>
                </thead>
                <tbody id="overviewBody">
                    <tr><td colspan="8" class="loading">Loading strategies...</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <script>
        let allRows = [];
        let sortKey = 'sharpe_ratio';
        let sortDir = 'desc';

        function fmt(val, isPercent) {
            if (val === null || val === undefined) return '—';
            const n = parseFloat(val);
            if (isNaN(n)) return '—';
            if (isPercent) {
                return (n * 100).toFixed(2) + '%%';
            }
            return n.toFixed(3);
        }

        // Columns: key → higherIsBetter
        const COL_DIR = {
            sharpe_ratio: true,
            cagr:         true,
            max_drawdown: true,   // less negative = better, so higher value = better
            volatility:   false,
            total_return: true,
            calmar_ratio: true,
            omega_ratio:  true,
        };

        let colStats = {};

        function computeColStats(rows) {
            const stats = {};
            for (const col of Object.keys(COL_DIR)) {
                const vals = rows
                    .map(r => r[col])
                    .filter(v => v !== null && v !== undefined)
                    .map(parseFloat)
                    .filter(n => !isNaN(n));
                if (vals.length < 2) continue;
                stats[col] = { min: Math.min(...vals), max: Math.max(...vals) };
            }
            return stats;
        }

        function cellStyle(val, col) {
            if (val === null || val === undefined) return '';
            const n = parseFloat(val);
            if (isNaN(n)) return '';
            const s = colStats[col];
            if (!s || s.max === s.min) return '';
            let pct = (n - s.min) / (s.max - s.min);
            if (!COL_DIR[col]) pct = 1 - pct;
            const hue = Math.round(pct * 120);   // 0 = red, 120 = green
            return `background-color: hsla(${hue}, 80%%, 45%%, 0.18);`;
        }

        function renderTable(rows) {
            const tbody = document.getElementById('overviewBody');
            if (rows.length === 0) {
                tbody.innerHTML = '<tr><td colspan="8" class="error">No strategies found. Run: python scripts/run_backtest.py --all</td></tr>';
                return;
            }

            tbody.innerHTML = rows.map(r => `
                <tr onclick="window.location='/strategy/${r.key}'">
                    <td><a class="strategy-link" href="/strategy/${r.key}">${r.key}</a></td>
                    <td style="${cellStyle(r.sharpe_ratio, 'sharpe_ratio')}">${fmt(r.sharpe_ratio, false)}</td>
                    <td style="${cellStyle(r.cagr, 'cagr')}">${fmt(r.cagr, true)}</td>
                    <td style="${cellStyle(r.max_drawdown, 'max_drawdown')}">${fmt(r.max_drawdown, true)}</td>
                    <td style="${cellStyle(r.volatility, 'volatility')}">${fmt(r.volatility, true)}</td>
                    <td style="${cellStyle(r.total_return, 'total_return')}">${fmt(r.total_return, true)}</td>
                    <td style="${cellStyle(r.calmar_ratio, 'calmar_ratio')}">${fmt(r.calmar_ratio, false)}</td>
                    <td style="${cellStyle(r.omega_ratio, 'omega_ratio')}">${fmt(r.omega_ratio, false)}</td>
                </tr>
            `).join('');
        }

        function sortTable(key) {
            if (sortKey === key) {
                sortDir = sortDir === 'asc' ? 'desc' : 'asc';
            } else {
                sortKey = key;
                sortDir = 'desc';
            }

            document.querySelectorAll('.sort-btn').forEach(btn => {
                btn.className = 'sort-btn';
            });
            const activeBtn = event.target;
            activeBtn.className = 'sort-btn ' + sortDir;

            allRows.sort((a, b) => {
                const av = a[key], bv = b[key];
                if (av === null || av === undefined) return 1;
                if (bv === null || bv === undefined) return -1;
                if (typeof av === 'string') return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
                return sortDir === 'asc' ? av - bv : bv - av;
            });

            renderTable(allRows);
        }

        function updateSummaryCards(rows) {
            document.getElementById('totalStrategies').textContent = rows.length;

            const withSharpe = rows.filter(r => r.sharpe_ratio !== null && r.sharpe_ratio !== undefined);
            if (withSharpe.length) {
                const best = withSharpe.reduce((a, b) => a.sharpe_ratio > b.sharpe_ratio ? a : b);
                document.getElementById('bestSharpe').textContent = parseFloat(best.sharpe_ratio).toFixed(2);
                document.getElementById('bestSharpeName').textContent = best.key;
            }

            const withCagr = rows.filter(r => r.cagr !== null && r.cagr !== undefined);
            if (withCagr.length) {
                const best = withCagr.reduce((a, b) => a.cagr > b.cagr ? a : b);
                document.getElementById('bestCagr').textContent = (best.cagr * 100).toFixed(1) + '%%';
                document.getElementById('bestCagrName').textContent = best.key;
            }

            const withDD = rows.filter(r => r.max_drawdown !== null && r.max_drawdown !== undefined);
            if (withDD.length) {
                const best = withDD.reduce((a, b) => a.max_drawdown > b.max_drawdown ? a : b);
                const pct = best.max_drawdown * 100;
                document.getElementById('lowestDD').textContent = pct.toFixed(1) + '%%';
                document.getElementById('lowestDDName').textContent = best.key;
            }
        }

        async function init() {
            try {
                const response = await fetch('/api/strategies/summary');
                allRows = await response.json();

                allRows.sort((a, b) => {
                    const av = a.sharpe_ratio, bv = b.sharpe_ratio;
                    if (av === null || av === undefined) return 1;
                    if (bv === null || bv === undefined) return -1;
                    return bv - av;
                });

                colStats = computeColStats(allRows);
                updateSummaryCards(allRows);
                renderTable(allRows);
            } catch (err) {
                document.getElementById('overviewBody').innerHTML =
                    '<tr><td colspan="8" class="error">Error loading strategies: ' + err.message + '</td></tr>';
            }
        }

        document.addEventListener('DOMContentLoaded', () => {
            init();
            // Auto-refresh every 10 seconds
            setInterval(init, 10000);
        });
    </script>
</body>
</html>
""" % {"shared_css": _SHARED_CSS}


# ---------------------------------------------------------------------------
# Strategy detail page (/strategy/<key>)
# ---------------------------------------------------------------------------

_DETAIL_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>%(title)s — Strategy Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.min.js"></script>
    <style>
        %(shared_css)s

        .nav-bar {
            background: #f5f5f5;
            padding: 12px 30px;
            border-bottom: 1px solid #e0e0e0;
            display: flex;
            align-items: center;
            gap: 16px;
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

        .control-group { display: flex; flex-direction: column; gap: 5px; }
        .control-group label { font-weight: 600; color: #333; font-size: 0.9em; }
        .control-group select {
            padding: 10px;
            border: 2px solid #ddd;
            border-radius: 6px;
            font-size: 1em;
            background: white;
            cursor: pointer;
            transition: border-color 0.3s;
        }
        .control-group select:focus { outline: none; border-color: #667eea; }

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
        .tab-button:hover { background: #e8e8e8; color: #667eea; }
        .tab-button.active {
            color: #667eea;
            border-bottom: 3px solid #667eea;
            margin-bottom: -2px;
        }

        .tab-panel { display: none; }
        .tab-panel.active { display: block; animation: fadeIn 0.3s ease; }

        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

        .chart-container { position: relative; height: 400px; margin-bottom: 30px; }

        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }

        .metric-card {
            background: linear-gradient(135deg, #667eea 0%%, #764ba2 100%%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        .metric-card h3 { font-size: 0.9em; text-transform: uppercase; opacity: 0.9; margin-bottom: 10px; }
        .metric-card .value { font-size: 2em; font-weight: bold; }

        .metrics-table {
            width: 100%%;
            border-collapse: collapse;
            margin-bottom: 30px;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }
        .metrics-table thead { background: #667eea; color: white; }
        .metrics-table th { padding: 15px; text-align: left; font-weight: 600; }
        .metrics-table td { padding: 12px 15px; border-bottom: 1px solid #e0e0e0; }
        .metrics-table tbody tr:hover { background: #f9f9f9; }
        .metrics-table tbody tr:last-child td { border-bottom: none; }

        .transactions-table { width: 100%%; border-collapse: collapse; font-size: 0.95em; }
        .transactions-table thead { background: #f0f0f0; }
        .transactions-table th {
            padding: 12px; text-align: left; font-weight: 600;
            color: #333; border-bottom: 2px solid #ddd;
        }
        .transactions-table td { padding: 10px 12px; border-bottom: 1px solid #e0e0e0; }
        .transactions-table tbody tr:hover { background: #f9f9f9; }

        @media (max-width: 768px) {
            .header h1 { font-size: 1.8em; }
            .tabs { flex-wrap: wrap; }
            .tab-button { flex: 1 1 50%%; padding: 15px; }
            .metrics-grid { grid-template-columns: 1fr; }
            .chart-container { height: 300px; }
            .controls { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Strategy Backtest Dashboard</h1>
            <p>Interactive visualization of portfolio optimization results</p>
        </div>

        <div class="nav-bar">
            <a href="/" class="btn">← All Strategies</a>
        </div>

        <div class="controls" id="controls">
            <div class="control-group">
                <label>Strategies:</label>
                <div id="strategySelectors"></div>
                <button class="btn" onclick="addStrategyRow()" style="margin-top: 8px;">+ Add Strategy</button>
            </div>
        </div>

        <div class="tabs">
            <button class="tab-button active" onclick="showTab('overview', event)">Strategy Overview</button>
            <button class="tab-button" onclick="showTab('portfolio', event)">Portfolio Value</button>
            <button class="tab-button" onclick="showTab('drawdown', event)">Drawdown</button>
            <button class="tab-button" onclick="showTab('weights', event)">Weights</button>
            <button class="tab-button" onclick="showTab('monthly', event)">Monthly Returns</button>
            <button class="tab-button" onclick="showTab('rolling', event)">Rolling Metrics</button>
            <button class="tab-button" onclick="showTab('transactions', event)">Transactions</button>
        </div>

        <div class="content">
            <!-- Strategy Overview Tab -->
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
                <h2 style="display: flex; justify-content: space-between; align-items: center;">
                    Portfolio Value Over Time
                    <button class="btn" onclick="exportCSV('portfolio')" style="font-size: 0.7em; padding: 6px 12px;">Export CSV</button>
                </h2>
                <div class="chart-container"><canvas id="portfolioChart"></canvas></div>
            </div>

            <!-- Drawdown Tab -->
            <div id="drawdown" class="tab-panel">
                <h2>Drawdown Analysis</h2>
                <div class="chart-container"><canvas id="drawdownChart"></canvas></div>
            </div>

            <!-- Weights Tab -->
            <div id="weights" class="tab-panel">
                <h2>Portfolio Weights Over Time</h2>
                <div class="chart-container"><canvas id="weightsChart"></canvas></div>
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
                <div class="chart-container"><canvas id="rollingChart"></canvas></div>
            </div>

            <!-- Transactions Tab -->
            <div id="transactions" class="tab-panel">
                <h2 style="display: flex; justify-content: space-between; align-items: center;">
                    Transaction History
                    <button class="btn" onclick="exportCSV('transactions')" style="font-size: 0.7em; padding: 6px 12px;">Export CSV</button>
                </h2>
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
        const INITIAL_STRATEGY = %(initial_strategy)s;

        let charts = {};
        let availableStrategies = [];
        let loadedData = {};

        const CHART_COLORS = [
            { border: '#667eea', bg: 'rgba(102,126,234,0.1)' },
            { border: '#f59e0b', bg: 'rgba(245,158,11,0.1)' },
            { border: '#10b981', bg: 'rgba(16,185,129,0.1)' },
            { border: '#ec4899', bg: 'rgba(236,72,153,0.1)' },
            { border: '#f97316', bg: 'rgba(249,115,22,0.1)' },
            { border: '#6366f1', bg: 'rgba(99,102,241,0.1)' },
        ];

        function getStrategySelections() {
            return Array.from(document.querySelectorAll('.strategy-select'))
                .map(s => s.value).filter(v => v);
        }

        function addStrategyRow(initialValue) {
            const container = document.getElementById('strategySelectors');
            const isFirst = container.children.length === 0;
            const row = document.createElement('div');
            row.className = 'strategy-row';
            row.style.cssText = 'display:flex;align-items:center;gap:8px;margin-bottom:6px;';
            const optionsHtml = availableStrategies.map(s =>
                `<option value="${s}"${s === initialValue ? ' selected' : ''}>${s}</option>`
            ).join('');
            row.innerHTML = `
                <select class="strategy-select" onchange="handleStrategyChange()"
                    style="padding:8px;border-radius:6px;border:2px solid #ddd;min-width:200px;">
                    ${isFirst ? '' : '<option value="">-- none --</option>'}
                    ${optionsHtml}
                </select>
                ${isFirst ? '' : '<button onclick="removeStrategyRow(this)" style="background:#dc3545;color:white;border:none;border-radius:4px;padding:4px 8px;cursor:pointer;font-size:1em;">×</button>'}
            `;
            container.appendChild(row);
        }

        function removeStrategyRow(btn) {
            btn.parentElement.remove();
            handleStrategyChange();
        }

        function formatCurrency(value) {
            if (value === null || value === undefined) return '—';
            const num = parseFloat(value);
            if (isNaN(num)) return '—';
            return '£' + num.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        }

        function formatMetric(key, value) {
            if (value === null || value === undefined) return '—';

            if (key.toLowerCase().includes('value') || key.toLowerCase().includes('cost') ||
                key.toLowerCase().includes('capital') || key.toLowerCase() === 'final_value') {
                return formatCurrency(value);
            }

            const k = key.toLowerCase();
            const num = parseFloat(value);
            if (isNaN(num)) return String(value);

            // Always treat these as decimal fractions → multiply by 100
            if (k.includes('return') || k.includes('volatility') || k.includes('drawdown') || k === 'cagr') {
                return (num * 100).toFixed(2) + '%%';
            }

            if (k.includes('sharpe') || k.includes('sortino') || k.includes('calmar') || k.includes('omega')) {
                return num.toFixed(3);
            }

            if (k.includes('transaction') || k.includes('rebalance') || k.includes('count')) {
                return Math.round(num);
            }

            return num.toFixed(2);
        }

        async function initializeDashboard() {
            try {
                const response = await fetch('/api/strategies');
                availableStrategies = await response.json();

                if (availableStrategies.length === 0) {
                    document.querySelector('.content').innerHTML =
                        '<div class="error">No strategies found. Run: python scripts/run_backtest.py --all</div>';
                    return;
                }

                const initial = INITIAL_STRATEGY || availableStrategies[0];
                addStrategyRow(initial);
                await handleStrategyChange();
            } catch (error) {
                console.error('Error initializing dashboard:', error);
                document.querySelector('.content').innerHTML =
                    '<div class="error">Error loading strategies. Make sure to run: python scripts/run_backtest.py --all</div>';
            }
        }

        async function handleStrategyChange() {
            const strategies = getStrategySelections();
            if (strategies.length === 0) return;

            await Promise.all(strategies.map(s => {
                if (!loadedData[s]) return loadStrategyData(s);
                return Promise.resolve();
            }));

            updateDashboard(strategies);
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

        function updateDashboard(strategies) {
            const dataList = strategies.map(s => loadedData[s]).filter(d => d);
            if (dataList.length === 0) return;

            const headerRow = document.getElementById('metricsHeaderRow');
            headerRow.innerHTML = '<th>Metric</th>' + strategies.map(s => `<th>${s}</th>`).join('');

            displayMetrics(dataList, strategies);
            displayPortfolioChart(dataList, strategies);
            displayDrawdownChart(dataList, strategies);
            displayWeightsChart(dataList[0], strategies[0]);
            displayTransactions(dataList[0]);
            loadMonthlyReturns(strategies[0]);
        }

        function displayMetrics(dataList, names) {
            const tbody = document.getElementById('metricsBody');
            tbody.innerHTML = '';

            const metricKeys = Object.keys(dataList[0].metrics || {});
            for (const key of metricKeys) {
                const row = document.createElement('tr');
                let html = `<td><strong>${key}</strong></td>`;
                for (const data of dataList) {
                    html += `<td>${formatMetric(key, (data.metrics || {})[key])}</td>`;
                }
                row.innerHTML = html;
                tbody.appendChild(row);
            }
        }

        function displayPortfolioChart(dataList, names) {
            const ctx = document.getElementById('portfolioChart').getContext('2d');
            if (charts.portfolio) charts.portfolio.destroy();

            const dates = (dataList[0].portfolio_history || []).map(p => p.date || p.timestamp).slice(0, 100);

            const datasets = dataList.map((data, i) => {
                const color = CHART_COLORS[i %% CHART_COLORS.length];
                return {
                    label: names[i],
                    data: (data.portfolio_history || []).map(p => p.total_value).slice(0, 100),
                    borderColor: color.border,
                    backgroundColor: color.bg,
                    tension: 0.4,
                    pointRadius: 0,
                    borderWidth: 2,
                };
            });

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
                    scales: { y: { beginAtZero: false, ticks: { callback: v => formatCurrency(v) } } }
                }
            });
        }

        function displayDrawdownChart(dataList, names) {
            const ctx = document.getElementById('drawdownChart').getContext('2d');
            if (charts.drawdown) charts.drawdown.destroy();

            const dates = (dataList[0].portfolio_history || []).slice(0, 100).map(p => p.date || p.timestamp);

            const datasets = dataList.map((data, i) => {
                const portfolio = (data.portfolio_history || []).slice(0, 100);
                const values = portfolio.map(p => p.total_value);
                const runningMax = values.reduce((acc, val) => {
                    acc.push(acc.length === 0 ? val : Math.max(acc[acc.length - 1], val));
                    return acc;
                }, []);
                const drawdown = values.map((val, j) => ((val - runningMax[j]) / runningMax[j]) * 100);
                const color = CHART_COLORS[i %% CHART_COLORS.length];
                return {
                    label: names[i],
                    data: drawdown,
                    borderColor: color.border,
                    backgroundColor: color.bg.replace('0.1', '0.2'),
                    tension: 0.4,
                    pointRadius: 0,
                    borderWidth: 2,
                    fill: true,
                };
            });

            charts.drawdown = new Chart(ctx, {
                type: 'line',
                data: { labels: dates, datasets: datasets },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: { y: { max: 0, ticks: { callback: v => v + '%%' } } },
                    plugins: { legend: { display: true, position: 'top' } }
                }
            });
        }

        function displayWeightsChart(data1, name1) {
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
                    return val > 1 ? val : val * 100;
                }).slice(0, 100);

                return {
                    label: symbol,
                    data: values,
                    backgroundColor: colors[idx %% colors.length],
                    borderColor: colors[idx %% colors.length],
                    pointRadius: 0,
                    borderWidth: 1,
                    fill: true,
                    tension: 0.3,
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
                            ticks: { callback: v => v.toFixed(0) + '%%' }
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

        function showTab(tabName, event) {
            document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
            document.querySelectorAll('.tab-button').forEach(b => b.classList.remove('active'));
            document.getElementById(tabName).classList.add('active');
            if (event) event.target.classList.add('active');
            if (tabName === 'rolling') loadRollingMetrics();
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
                            const color = val >= 0
                                ? `rgba(40,167,69,${Math.min(Math.abs(val)/5, 0.8)})`
                                : `rgba(220,53,69,${Math.min(Math.abs(val)/5, 0.8)})`;
                            html += `<td style="background:${color}; text-align:center; font-weight:600;">${val.toFixed(1)}%%</td>`;
                        } else {
                            html += '<td style="text-align:center; color:#ccc;">-</td>';
                        }
                    }
                    const annualReturn = (yearReturn - 1) * 100;
                    const annualColor = annualReturn >= 0 ? '#28a745' : '#dc3545';
                    html += `<td style="text-align:center; font-weight:700; color:${annualColor};">${annualReturn.toFixed(1)}%%</td>`;
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
            const strategies = getStrategySelections();
            if (strategies.length === 0) return;

            const metric = document.getElementById('rollingMetricSelect').value;
            const window = document.getElementById('rollingWindowSelect').value;
            const metricLabels = { sharpe: 'Sharpe Ratio', volatility: 'Volatility (%%)', sortino: 'Sortino Ratio' };

            try {
                const results = await Promise.all(strategies.map(s =>
                    fetch(`/api/strategy/${s}/rolling?metric=${metric}&window=${window}`).then(r => r.json())
                ));

                if (results[0].error) { console.error(results[0].error); return; }

                const ctx = document.getElementById('rollingChart').getContext('2d');
                if (charts.rolling) charts.rolling.destroy();

                const dates = results[0].data.map(d => d.date);

                const datasets = results.map((result, i) => {
                    if (result.error) return null;
                    const color = CHART_COLORS[i %% CHART_COLORS.length];
                    return {
                        label: `Rolling ${metricLabels[metric]} (${window}d) - ${strategies[i]}`,
                        data: result.data.map(d => d.value),
                        borderColor: color.border,
                        backgroundColor: color.bg,
                        tension: 0.4,
                        pointRadius: 0,
                        borderWidth: 2,
                        fill: true,
                    };
                }).filter(Boolean);

                charts.rolling = new Chart(ctx, {
                    type: 'line',
                    data: { labels: dates, datasets: datasets },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: true, position: 'top' } },
                        scales: {
                            y: {
                                ticks: { callback: v => metric === 'volatility' ? v.toFixed(1) + '%%' : v.toFixed(2) }
                            }
                        }
                    }
                });
            } catch (error) {
                console.error('Error loading rolling metrics:', error);
            }
        }

        function exportCSV(type) {
            const strategies = getStrategySelections();
            if (!strategies.length) return;
            window.open(`/api/strategy/${strategies[0]}/export?type=${type}`, '_blank');
        }

        document.addEventListener('DOMContentLoaded', () => {
            initializeDashboard();
            // Auto-refresh loaded strategy data every 10 seconds
            setInterval(async () => {
                const strategies = getStrategySelections();
                if (strategies.length === 0) return;
                // Bust the cache so fresh data is fetched
                strategies.forEach(s => delete loadedData[s]);
                await handleStrategyChange();
            }, 10000);
        });
    </script>
</body>
</html>
"""


@bp.route("/")
def overview():
    """Serve the strategies overview page."""
    return render_template_string(_OVERVIEW_HTML)


@bp.route("/strategy/")
@bp.route("/strategy/<strategy_key>")
def strategy_detail(strategy_key: str = None):
    """Serve the strategy detail page."""
    title = strategy_key or "Strategy"
    initial = f'"{strategy_key}"' if strategy_key else "null"
    html = _DETAIL_HTML % {
        "shared_css": _SHARED_CSS,
        "title": title,
        "initial_strategy": initial,
    }
    return render_template_string(html)
