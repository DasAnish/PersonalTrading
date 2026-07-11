# Nightly / one-command pipeline

`python scripts/run_nightly.py` — idempotent; run nightly via Task Scheduler
or by hand when sitting down to work. Order:

| # | Step | Script | On failure |
|---|------|--------|------------|
| 1 | git sync | (inline) fetch + ff-only | **abort** on dirty tracked files; diverged branch recorded, not merged |
| 2 | data refresh | `scripts/refresh_data.py` | IB Gateway down tolerated → continue on cache, `data_refreshed=false` (exit 2 = gateway down) |
| 3 | sanity + freshness gate | `scripts/validate_cache.py` | gate fail → **abort analysis** (override `--force`) |
| 4 | analysis | `scripts/run_full_analysis.py` | abort |
| 5 | index rebuild | `scripts/rebuild_index.py` | abort |
| 6 | archive | (inline) → `results/runs/<run_id>/` | — |

Manifest: `results/run_manifest.json` (+ copy in run archive). Fields: run id,
git state (head/ahead/behind/diverged), per-symbol `data_end_dates`,
`panel_end`, stale/missing symbols, step exit codes + timings, `ok`.

Flags: `--fast` (skip PBO sweeps), `--skip-git`, `--skip-refresh`,
`--skip-analysis` (data steps only), `--max-stale-days N` (default 7),
`--force` (analysis despite failed gate).

## Pieces, standalone

- `scripts/refresh_data.py [--symbols A,B]` — refresh parquet cache while
  gateway up; writes `results/data_refresh.json`.
- `scripts/validate_cache.py [--max-stale-days N]` — content checks (dupes,
  gaps, NaNs, non-positive closes, absurd daily moves) + freshness gate;
  writes `results/cache_validation.json`; exit 1 = gate failed.
- `scripts/snapshot_nav.py [--strategy KEY]` — daily account NAV + positions
  to `live_tracking/nav_history.csv` + `live_tracking/positions/<date>.json`
  (idempotent per day; optional target-weights record for shortfall math).
  Runs automatically inside the nightly when the gateway is up.
- `scripts/rebuild_index.py [--dry-run]` — rebuild `strategies_index.json`
  from `results/strategies/*/` disk truth; adds per-strategy `config_hash`
  (sha256 of definition file) so run-over-run Sharpe diffs can separate
  "data moved" from "config changed", plus a `vintage` block
  (`min/max_data_end`, `mixed`) that flags part-rebuilt libraries — mixed
  vintages surface in the manifest, the API, and the dashboard banner.
- `scripts/recompute_metrics.py [--dry-run]` — regenerate every
  `metrics.json` from saved portfolio histories via the canonical
  `analytics.metrics.summarize_performance` (annualization inferred from
  series spacing — the 2026-07-10 audit found monthly series annualized
  with sqrt(252), inflating Sharpe ~4.6x). No backtests, no IB needed.

## Run archive / regression diffing

Each successful pipeline run copies `strategies_index.json` plus every
strategy's `metrics.json`, `info.json`, `validation.json`,
`overfitting_analysis.json` to `results/runs/<run_id>/`. `results/` is
gitignored — the archive is local history. Diff two runs by comparing their
`strategies_index.json` metrics for entries with equal `config_hash`.

## Related research tooling

- `scripts/build_meta_portfolio.py` — decorrelated blend across
  validation-PASS strategies (greedy Sharpe under `--max-corr`, inverse-vol
  weights) → `results/meta_portfolio.json`. Feeds the manual rebalance.
- `scripts/extend_history.py` — splice long-history proxies
  (`strategy_definitions/proxy_map.json`) onto cached ETF series →
  `data/cache_extended/`; refuses proxies whose overlap correlation
  < `--min-corr`. Attacks the short-T constraint blocking SPA.

## Task Scheduler (optional)

The script is safe unattended (never places orders; gateway-down tolerated):

```powershell
schtasks /Create /TN "PersonalTrading nightly" /SC DAILY /ST 06:30 ^
  /TR "cmd /c cd /d C:\Users\dasan\OneDrive\Desktop\Projects\PersonalTrading && python scripts\run_nightly.py --fast >> results\nightly.log 2>&1"
```

Machine asleep = run skipped silently, so don't trust the schedule: check
`run_manifest.json`'s `started_at` at session start (dashboard banner reads
the same file).
