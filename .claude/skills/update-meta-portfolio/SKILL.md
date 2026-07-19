---
name: update-meta-portfolio
description: Re-slate the Claude PM meta portfolio — create the next versioned meta_claude_pm_N, backtest it, and register it for forward OOS tracking. Never edit a registered slate in place.
---

# Update Meta Portfolio (Claude PM slate)

Versioned re-slate workflow. Slates are pre-registered forward-OOS experiments:
**a registered slate's weights are FROZEN forever**. Any change — weights,
sleeves, cash — becomes a NEW version `meta_claude_pm_<N+1>`. Editing an
existing slate in place destroys its out-of-sample record.

## Inputs

Ask the user (or take from their message):
- New sleeve list (strategy keys, must exist in `strategy_definitions/`) + weights
- Cash weight (default 0.10)
- Effective-from date (default: tomorrow)
- Rationale for the change (goes in the description)

## Steps

1. Find current highest version: `ls strategy_definitions/portfolios/meta_claude_pm_*.json`.
   New key = `meta_claude_pm_<N+1>`. Do NOT modify or delete older versions.
2. Write `strategy_definitions/portfolios/meta_claude_pm_<N+1>.json`:
   - `"class": "MetaPortfolioStrategy"`, `"type": "portfolio"`
   - `"parameters": {"weights": [...], "cash_weight": ...}` — weights list is
     RELATIVE (normalised internally), same order as `underlying`;
     `underlying` entries are `"allocations/<key>"` / `"composed/<key>"` refs
   - `"effective_from": "<YYYY-MM-DD>"` (informational; OOS clock start)
   - `"name": "Meta: Claude PM Slate <N+1>"`; description = date chosen,
     sleeve weights, rationale, "weights frozen" note
   - Tags: `["ensemble", "pm-slate", "pre-registered", "paper-trading", "mech:meta"]`
3. Backtest: `python scripts/run_backtest.py --use-definitions --strategy meta_claude_pm_<N+1>`
   Sanity-check Sharpe / MaxDD vs previous slate before registering.
4. Register (freezes backtest block + kill criteria; `registered_at` =
   effective-from date, `review_date` = +3 months):

   ```
   python -c "import json; from analytics.registrations import register, backtest_block_from_metrics; m=json.load(open('results/strategies/meta_claude_pm_<N+1>/metrics.json')); register('meta_claude_pm_<N+1>', backtest_block_from_metrics(m), review_date='<+3mo>', registered_at='<effective_from>T00:00:00')"
   ```

5. `python scripts/check_registrations.py` — verify status file includes the new key.
6. Keep the old slate's registration ACTIVE (its OOS record continues) unless
   the user explicitly retires it (`remove_registration`).
7. Commit definition (+ strategies code if touched). `live_tracking/` and
   `results/` are gitignored — registration lives on disk only.
8. Update memory (`validity_doctrine` / session memory) with the new slate.

## Reminders

- Research/reporting only — never place orders (CLAUDE.md rule).
- DSR verdicts use global-pool N; a FAIL is pool-size, judge sleeves on
  mechanism diversity + k-fold + drawdown, not DSR alone.
