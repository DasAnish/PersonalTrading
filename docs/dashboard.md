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
| `GET /api/strategies/summary` | Key metrics (Sharpe, CAGR, max DD, volatility, Calmar, Omega) for every strategy — used by the overview page |
| `GET /api/strategy/<key>` | Full JSON: portfolio_history, transactions, weights_history, metrics, info |
| `GET /api/strategy/<key>/monthly_returns` | Monthly returns matrix for the heatmap tab |
| `GET /api/strategy/<key>/rolling?metric=sharpe\|volatility\|sortino&window=63` | Rolling metric series |
| `GET /api/strategy/<key>/export?type=portfolio\|transactions\|weights` | CSV download of the requested series |
| `GET /api/strategy/<key>/overfitting` | Contents of `overfitting_analysis.json` (DSR, PBO, k-fold verdicts); 404 with a `hint` if not yet run |
| `GET /api/strategy/<key>/stress_test` | Contents of `stress_test.json` (crisis-period metrics + leave-one-crisis-out scenario removal); 404 with a `hint` if not yet run (`--stress-test`) |
| `GET /api/compare?keys=a,b,c` | Side-by-side comparison across up to 10 strategies |
| `GET /api/compare/<key1>/<key2>` | Legacy two-strategy comparison endpoint |
| `GET /info` | Glossary page defining every term used on the dashboard |
| `POST /api/run/<key>` | Launch backtest → validate → overfitting for one definition as background subprocesses (fresh code each run). Optional body `{"steps": [...]}` to run a subset. Returns `202` + `job_id` |
| `GET /api/run/status/<job_id>` | Job state (`queued`/`running`/`done`/`failed`/`interrupted`), per-step exit codes + logs; when `done`, embeds metrics/validation/overfitting results |
| `GET /api/run/jobs` | Recent jobs, newest first. Jobs persist to `results/jobs/<id>/job.json` and survive server restarts; in-flight jobs from a dead process show as `interrupted` |
| `GET /api/data-freshness` | Cache panel end date, stale/missing/corrupt symbols, freshness-gate verdict + last pipeline run (from `results/cache_validation.json` / `run_manifest.json`). Drives the overview banner |

Run-job example (what the build agents use):
```bash
curl -s -X POST localhost:5000/api/run/hrp_ward
# {"job_id": "42435b3bcee3", "state": "queued", "status_url": "/api/run/status/42435b3bcee3", ...}

curl -s localhost:5000/api/run/status/42435b3bcee3
# {"state": "done", "step_results": {"backtest": {"exit_code": 0, ...}, ...},
#  "results": {"metrics": {...}, "validation": {...}, "overfitting": {...}}}
```
Jobs run at most 2 at a time (`MAX_CONCURRENT_JOBS` in `scripts/server/jobs.py`);
step logs live under `results/jobs/<job_id>/`. The runner only shells out to the
research scripts — it can never place orders.

Example:
```bash
curl http://localhost:5000/api/strategy/hrp_single
# { "key": "hrp_single", "metrics": {"total_return": 0.45, "sharpe_ratio": 0.67, ...}, ... }

curl http://localhost:5000/api/strategy/hrp_single/overfitting
# { "dsr": {...}, "pbo": {...}, "kfold": {"fold_sharpes": [...], "fraction_positive": 0.8, "verdict": "PASS", ...} }
```

## Static Reports

`analytics/report.py` renders the same underlying JSON (metrics, stress test,
overfitting analysis) into a persisted Markdown/HTML report per strategy —
useful for sharing outside the dashboard or archiving a run's conclusions.

```bash
# Generate for one strategy (writes results/strategies/<key>/report.md)
python scripts/generate_report.py --strategy hrp_single

# Generate for every strategy in the index, markdown + HTML
python scripts/generate_report.py --all --format both

# Or generate automatically right after a backtest run
python scripts/run_backtest.py --all --stress-test --report
```

Missing optional inputs (no `--stress-test` run, no overfitting analysis)
degrade gracefully: those sections are replaced with a note and the command
to generate them, rather than causing the report to fail.

---

## Performance Notes

- Strategy data lazy-loaded only when selected
- Charts capped at 100 data points for responsiveness
- Loaded data cached in JS memory for the session
