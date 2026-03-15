# Web Dashboard

**File**: `scripts/serve_results.py`
**Stack**: Flask (backend) + Chart.js 3.9.1 (charts) + Vanilla JS

```bash
# 1. Generate results
python scripts/run_backtest.py --all

# 2. Start server
python scripts/serve_results.py

# 3. Open http://localhost:5000
```

---

## Features

- Strategy picker dropdown (loads data on demand)
- Comparison mode: select two strategies side-by-side
- Tabs: Overview, Portfolio Value, Drawdown, Weights, Transactions, Monthly Heatmap, Rolling Metrics
- CSV export endpoints
- Responsive layout (CSS Grid + Flexbox)

---

## API Endpoints

| Endpoint | Returns |
|----------|---------|
| `GET /` | Main HTML dashboard |
| `GET /api/strategies` | `["hrp_single", "trend_following", ...]` |
| `GET /api/strategy/<key>` | Full JSON: portfolio_history, transactions, weights_history, metrics, info |

Example:
```bash
curl http://localhost:5000/api/strategy/hrp_single
# { "key": "hrp_single", "metrics": {"total_return": 0.45, "sharpe_ratio": 0.67, ...}, ... }
```

---

## Performance Notes

- Strategy data lazy-loaded only when selected
- Charts capped at 100 data points for responsiveness
- Loaded data cached in JS memory for the session
