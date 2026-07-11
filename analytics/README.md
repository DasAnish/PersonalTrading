# analytics/

Performance metrics, overfitting analysis, and reporting — everything that turns a backtest's return series into a verdict.

## Metrics & summary
- `metrics.py` — Sharpe, Sortino, Calmar, VaR/CVaR, drawdown, rolling metrics. Annualization is **inferred from series spacing**, never hard-coded.
- `summary.py` — per-strategy summary aggregation
- `rebalance.py` — rebalance-level attribution

## Overfitting / validation stack
- `overfitting.py`, `overfitting_results.py` — Deflated Sharpe Ratio (DSR), Probability of Backtest Overfitting (PBO)
- `cpcv.py` — Combinatorial Purged Cross-Validation
- `bootstrap.py` — bootstrap resampling of returns
- `spa.py` — Hansen's Superior Predictive Ability test (the go/no-go gate)
- `composed_pbo.py` — PBO over composed strategies
- `validation.py` — orchestrates the full validation battery
- `family_matrix.py` — mechanism/family correlation matrix for multiple-testing control
- `stress_testing.py` — scenario / stress analysis

## Output
- `blend.py` — strategy blending / preferred-blend construction
- `report.py` — human-readable analysis reports
- `visualizations.py` — performance charts

See [../docs/overfitting.md](../docs/overfitting.md) for the methodology.
