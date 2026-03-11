# HRP Backtest Dashboard - User Guide

An interactive web-based dashboard for viewing and analyzing HRP backtest results with beautiful visualizations and detailed metrics.

## Quick Start

### 1. Run a Backtest (if you haven't already)

```bash
python scripts/run_hrp_backtest.py
```

This generates CSV files in the `results/` directory.

### 2. Start the Dashboard

**On Windows:**
```bash
scripts/start_dashboard.bat
```

**On macOS/Linux:**
```bash
bash scripts/start_dashboard.sh
```

**Or directly with Python:**
```bash
python scripts/serve_results.py
```

### 3. Open Your Browser

Navigate to: **http://localhost:5000**

You should see the dashboard with your backtest results.

## Features

### 📊 Dashboard Tabs

#### **Overview**
- **Performance Metrics Table** - Complete comparison of all metrics
- **Key Metrics Cards** - Visual cards showing:
  - Total Return (%)
  - Sharpe Ratio
  - Maximum Drawdown (%)
  - Volatility (%)

#### **Portfolio Value**
- Line chart showing portfolio value over time for both strategies
- Compares HRP Strategy (blue) vs Equal Weight (orange)
- Hover over the chart to see exact values on specific dates

#### **Drawdown**
- Shows the underwater plot (peak-to-trough decline)
- Helps visualize the worst periods during the backtest
- Maximum drawdown represents the largest loss from peak to trough

#### **Weights**
- Stacked area chart showing HRP portfolio composition over time
- Each color represents an asset (VUSA, SSLN, SGLN, IWRD)
- Shows how weights change at each rebalancing date

#### **Transactions**
- Detailed transaction history for both strategies
- Columns: Date, Symbol, Quantity, Price, Total Cost, Transaction Fee
- Shows all buy/sell orders executed during backtesting

## Understanding the Metrics

### Key Performance Indicators

| Metric | Meaning | Better If |
|--------|---------|-----------|
| **Total Return (%)** | Overall gain/loss from initial capital | Higher (positive) |
| **CAGR (%)** | Compound Annual Growth Rate | Higher |
| **Sharpe Ratio** | Risk-adjusted return (return per unit of risk) | Higher |
| **Max Drawdown (%)** | Largest peak-to-trough decline | Closer to 0 (smaller) |
| **Volatility (%)** | Annualized standard deviation (risk) | Lower |
| **Total Transactions** | Number of trades executed | Depends on strategy |
| **Total Costs (£)** | Transaction fees paid | Lower |
| **Final Value (£)** | Ending portfolio value | Higher |

### Reading the Charts

**Portfolio Value Chart**
- Shows absolute portfolio value over time
- Useful for comparing strategies visually
- A rising line indicates positive returns

**Drawdown Chart**
- Red shaded area shows when portfolio is below its peak
- Deeper valleys = larger drawdowns
- Helps identify stressful periods

**Weights Chart**
- 100% stacked area = portfolio is always fully invested
- Each colored section = allocation to an asset
- Changes show rebalancing activity

## Interpreting Results

### HRP vs Equal Weight

**HRP Strategy Advantages:**
- Often shows lower volatility
- Better risk-adjusted returns (higher Sharpe ratio)
- More stable portfolio through diversification

**Equal Weight Advantages:**
- Simpler to understand
- Easier to implement
- Sometimes better in trending markets

## Troubleshooting

### Dashboard Won't Start

**Problem:** Port 5000 already in use
```
Address already in use
```

**Solution:**
```bash
# Kill the process on port 5000 (macOS/Linux)
lsof -i :5000 | grep LISTEN | awk '{print $2}' | xargs kill -9

# Or try a different port by editing serve_results.py:
# Change: app.run(debug=True, port=5000)
# To:     app.run(debug=True, port=5001)
```

### No Data Displayed

**Problem:** Results directory is empty
- Run the backtest first: `python scripts/run_hrp_backtest.py`
- Check that CSV files exist in `results/` directory

**Problem:** Charts show blank
- Wait a few seconds for data to load
- Refresh the page (Ctrl+R)
- Check browser console for errors (F12 > Console tab)

### Metrics Show "NaN"

This can occur when:
- Insufficient data for calculation
- All returns are negative (affects some metrics)
- Division by zero in some edge cases

This is normal and not an error.

## Advanced Usage

### Custom Port

Edit `scripts/serve_results.py` and change:

```python
if __name__ == "__main__":
    app.run(debug=True, port=5000)  # Change 5000 to your port
```

### Access from Another Computer

To allow access from other computers on your network:

```python
if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)  # 0.0.0.0 = all interfaces
```

Then access from other machines using: `http://<your-ip>:5000`

### Export Data

You can access raw JSON data via the API:

```bash
# Get all dashboard data as JSON
curl http://localhost:5000/api/data > backtest_data.json
```

## Performance Tips

- **Large datasets**: If you have many months of data, charts may be slower
- **Browser**: Use a modern browser (Chrome, Firefox, Safari, Edge)
- **Refresh rate**: Dashboard doesn't auto-refresh; refresh manually to see updated data
- **Responsiveness**: Dashboard is mobile-friendly and adapts to screen size

## Features Coming Soon

- Real-time auto-refresh
- Export to PDF report
- Comparison of multiple backtests
- Parameter sensitivity analysis
- Factor analysis overlay

## Technical Details

### Architecture

```
Flask Backend (serve_results.py)
    ↓
    ├─ /                    → HTML dashboard
    ├─ /api/data           → JSON API endpoint
    └─ Results CSVs        ← Read from disk

Frontend (HTML/CSS/JavaScript)
    ↓
    ├─ Chart.js            → Visualizations
    ├─ Vanilla JS          → Interactivity
    └─ Responsive CSS      → Mobile support
```

### Data Flow

1. Backtest generates CSV files in `results/` directory
2. Dashboard server loads CSV files on demand
3. Data is formatted into JSON
4. Frontend fetches JSON via `/api/data` endpoint
5. Charts.js renders interactive visualizations
6. User explores results via browser

### Files Generated by Backtest

- `hrp_portfolio_history.csv` - Daily portfolio state for HRP
- `equal_weight_history.csv` - Daily portfolio state for equal weight
- `hrp_transactions.csv` - Trade list for HRP
- `equal_weight_transactions.csv` - Trade list for equal weight
- `performance_comparison.csv` - Metrics comparison table

## Browser Compatibility

| Browser | Status |
|---------|--------|
| Chrome | ✅ Full support |
| Firefox | ✅ Full support |
| Safari | ✅ Full support |
| Edge | ✅ Full support |
| IE 11 | ❌ Not supported |

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `1-5` | Jump to tabs (Overview, Portfolio, Drawdown, Weights, Transactions) |

## FAQ

**Q: Can I edit the backtest directly from the dashboard?**
A: No, the dashboard is read-only. To change parameters, edit `scripts/run_hrp_backtest.py` and re-run the backtest.

**Q: Why are some metrics "NaN"?**
A: This usually means there's insufficient data or a mathematical edge case (like division by zero). This is normal.

**Q: Can I access the dashboard from my phone?**
A: Yes! The dashboard is fully responsive and works on mobile devices.

**Q: How do I refresh the data?**
A: Run the backtest again and refresh your browser page.

**Q: Can I run multiple strategies and compare?**
A: Currently the dashboard shows HRP vs Equal Weight. For custom comparisons, edit `scripts/run_hrp_backtest.py`.

## Support

For issues or feature requests:
1. Check the troubleshooting section above
2. Review the backtest logs: `python scripts/run_hrp_backtest.py`
3. Open an issue on GitHub: https://github.com/DasAnish/PersonalTrading/issues

## Technical Stack

- **Backend**: Python Flask
- **Frontend**: HTML5 + CSS3 + Vanilla JavaScript
- **Charts**: Chart.js 3.9.1
- **Data Format**: CSV (input) → JSON (API)
- **Styling**: Responsive CSS Grid + Flexbox

---

**Last Updated**: February 2026
**Version**: 1.0.0
