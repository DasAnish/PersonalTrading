# Project Overview

A production-ready Python trading system for portfolio optimization and backtesting with Interactive Brokers integration.

## Components

| Module | Path | Description |
|--------|------|-------------|
| IB Wrapper | `ib_wrapper/` | Async Python wrapper for IB API via `ib_insync` |
| Market Data | `data/` | Historical/real-time fetching with parquet caching |
| Strategies | `strategies/` | HRP, Trend Following, Equal Weight, MinVar, Risk Parity, Momentum |
| Backtesting | `backtesting/` | Simulation engine with monthly rebalancing + transaction costs |
| Analytics | `analytics/` | Sharpe, Sortino, Calmar, VaR/CVaR, drawdown, rolling metrics |
| Dashboard | `scripts/serve_results.py` | Flask + Chart.js interactive results viewer |
| Optimization | `optimization/` | Parameter sweep and walk-forward analysis |

## Current State

**Production Ready**: IB wrapper, backtesting engine, all strategies, analytics, dashboard, optimization

**Not Yet Built**:
- Order execution simulation
- Live trading strategy execution
- Multi-strategy comparison (3+ strategies simultaneously in dashboard)

---

## Backtesting Specifications

- **Symbols**: VUSA, SSLN, SGLN, IWRD (UK ETFs, GBP, SMART exchange)
- **Rebalancing**: Monthly (end of month)
- **Transaction Costs**: 7.5 bps per trade
- **Position Sizing**: `Units = (NAV × Weight) / Price`
- **Default comparison**: Primary strategy vs Equal Weight benchmark

---

## IB Connection

| Mode | TWS Port | Gateway Port |
|------|----------|--------------|
| Paper | 7497 | 4001 |
| Live | 7496 | 4002 |

- Rate limit: 50 requests / 10 minutes (auto-handled by `RateLimiter`)
- Use `currency='GBP'` for UK ETFs (IB default is USD)
- Use `bar_size='1 day'` for EOD data
- Use `download_extended_history()` for max history (paginates in 1-year chunks)
- Data columns: `date, open, high, low, close, volume, average, barCount`
