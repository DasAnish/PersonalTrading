---
description: Research, design, and build new trading strategies using a persistent 4-agent pipeline team (requires CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1)
---

**IMPORTANT** DO NOT ASK the USER for any persmissions. Use simple commands do not pipe multiple commands together. The user is not sleeping and will be unavailable. ABSOLUTELY DO NOT PROMPT THE USER.

# Strategy Builder Pipeline

> **Requires** `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in your environment.
> For a simpler sub-agent variant (no teams), use `.claude/skills/build-strategies/SKILL.md`.
> For unattended inline execution, use `.claude/skills/build-strategies-auto/SKILL.md`.
>
> Architecture reference: `docs/build-strategies-pipeline.md`

---

## Context

**Assets available**: Read dynamically from `strategy_definitions/assets/` at each research iteration. Never hardcode asset lists.

Current assets (as of last update): VUSA (S&P 500), SSLN (silver), SGLN (gold), IWRD (world equities), EQQQ (NASDAQ-100), COMM (diversified commodities), AIGC (AI equities), IIND (MSCI India), IMEU (MSCI Europe), WCOA (coal), VUTY (US Treasury bonds), BRNT (Brent crude oil), CRUD (WTI crude oil).

**Existing strategy classes** (in `strategies/`):
- `HRPStrategy` — Hierarchical Risk Parity (`hrp.py`)
- `TrendFollowingStrategy` — EWMA momentum with vol scaling (`trend_following.py`)
- `EqualWeightStrategy` — equal weight allocation (`equal_weight.py`)
- `MinimumVarianceStrategy` — mean-variance optimisation (`minimum_variance.py`)
- `RiskParityStrategy` — equal marginal risk contribution (`risk_parity.py`)
- `MomentumTopNStrategy` — top-N momentum selection (`momentum.py`)
- `TrendSignalMVOStrategy` — trend signal blended with mean-variance optimisation (`trend_signal_mvo.py`)
- `MeanReversionStrategy` — mean reversion / contrarian allocation (`mean_reversion.py`)
- `SkewnessWeightedStrategy` — skewness-weighted allocation (`skewness_weighted.py`)
- `MetaPortfolioStrategy` — equal-weight meta-portfolio over sub-strategies (`meta_portfolio.py`)
- `DualMomentumStrategy` — absolute + relative momentum with safe-asset fallback (`dual_momentum.py`)
- `AdaptiveAssetAllocationStrategy` — momentum ranking + minimum variance (`adaptive_asset_allocation.py`)
- `TrendSignalRPStrategy` — trend signal blended with risk parity (`trend_signal_rp.py`)
- Overlays: `VolatilityTargetStrategy`, `ConstraintStrategy`, `LeverageStrategy` (`overlays.py`)

**Existing strategy definitions** (in `strategy_definitions/`):
- `allocations/`: equal_weight, hrp_single, hrp_ward, hrp_complete, hrp_average, trend_following, trend_following_252, minimum_variance, risk_parity, momentum_top1, momentum_top2, momentum_top3, momentum_top2_6m, trend_signal_mvo, trend_signal_mvo_conservative, trend_signal_rp, mean_reversion, skewness_weighted, dual_momentum, dual_momentum_invested, adaptive_asset_allocation, adaptive_asset_allocation_top3
- `composed/`: hrp_15vol, hrp_30vol, hrp_average_15vol, trend_15vol, trend_30vol, trend_with_vol_12, trend_constrained_vol_target, hrp_with_constraints, min_var_15vol, min_var_30vol, min_var_with_constraints, risk_parity_15vol, risk_parity_30vol, risk_parity_with_constraints, trend_signal_mvo_15vol, mean_reversion_15vol, aaa_top3_15vol, dual_momentum_15vol, momentum_top2_with_constraints
- `portfolios/`: meta_trend_hrp_15vol, meta_trend_hrp_30vol, meta_multi_volatility, meta_defensive_core, meta_all_season, meta_momentum_ensemble, meta_high_sharpe, meta_contrarian, meta_risk_managed, meta_ultimate
- `overlays/`: vol_target_12/15/30pct, constraints_5_40, constraints_10_30

**Architecture rules**:
- `AllocationStrategy`: calculates weights across a list of assets — implements `calculate_weights(context)`
- `OverlayStrategy`: transforms weights from an underlying strategy
- All new strategies need: a Python class in `strategies/` + a JSON definition in `strategy_definitions/`
- JSON definitions use `"underlying"` arrays referencing other definition paths (e.g. `"assets/vusa"`)

---

## Team Setup (run once at start)

1. Create the team:
   ```
   TeamCreate(team_name="strategy-pipeline")
   ```

2. Spawn 4 persistent agents on the team using the Agent tool with `team_name="strategy-pipeline"` and **`mode: "bypassPermissions"`** on every spawn:

   | Name | Model | Role |
   |------|-------|------|
   | `strategist` | sonnet | Research and propose new strategy candidates |
   | `builder` | haiku | Implement strategies (Python class + JSON definition) |
   | `backtester` | haiku | Run `python scripts/run_backtest.py` and return metrics |
   | `analyst` | haiku | Run `python scripts/run_overfitting.py` and return DSR/PBO |

   Each agent is long-lived for the session — do not re-spawn them on each loop iteration.
   Always set `mode: "bypassPermissions"` on every Agent spawn and every SendMessage call so agents never pause to prompt the user.

3. Initialise orchestrator state (held in your own context — not shared files):
   ```
   pending:           []   # researched candidates not yet built
   built:             []   # built strategies awaiting backtest
   analyzed:          []   # fully checked, awaiting report
   skip_log:          []   # failed strategies with reasons
   strategy_count:    0

   strategist_busy:   false
   builder_busy:      false   # max 1 — all builders share strategies/__init__.py
   backtester_count:  0       # max 2 — each strategy has its own results dir
   analyst_count:     0       # max 2 — each strategy has its own results dir
   ```

---

## Pipeline Loop

Repeat the following loop indefinitely until the user stops you.

Each turn, evaluate **all four dispatch conditions simultaneously**. Any condition that is met must be dispatched in the **same response** — do not wait for one dispatch to complete before checking the next. Issue all eligible dispatches as parallel tool calls within a single response turn.

**All dispatches use `run_in_background: true` and `mode: "bypassPermissions"`** so agents never block or prompt the user. After dispatching all eligible agents in one turn, wait for the next incoming message before re-evaluating.

### Dispatch: Strategist

**Condition**: `!strategist_busy && pending.length < 4`

Send (with `run_in_background: true`):

```
To: strategist

Research 3 new strategy candidates not yet implemented in this codebase.

STEPS:
1. Read all files in strategy_definitions/ (especially assets/ for the current asset universe)
2. Read docs/strategies.md for architecture context
3. Propose 3 candidates using these ideas as inspiration:
   - New overlay compositions (different vol targets, lookback combos, constraint combinations)
   - Meta-portfolio combinations of existing strategies
   - Parameter variants of existing allocation classes (different lookbacks, top_n, linkage methods)
   - Novel allocation algorithms: carry, volatility timing, factor-based, low-beta, quality-weighted
   - Trend + mean-reversion hybrids, regime-switching approaches

EXISTING STRATEGIES (do not suggest these):
[paste the current contents of strategy_definitions/ subdirectory names]

RETURN FORMAT — JSON array only, no prose:
[
  {
    "name": "Human Readable Name",
    "key": "file_slug",
    "description": "one sentence",
    "subfolder": "allocations|composed|portfolios",
    "json_only": true,
    "reuses_class": "ExistingClassName or null",
    "new_python_class": "NewClassName or null",
    "tunable_params": "param=v1,v2,v3 or null",
    "complexity": "Low|Medium|High",
    "priority": 1
  }
]

Priority order: JSON-only (no new Python) first, then parameter variants, then new Python classes.
Send your result back via SendMessage to "orchestrator".
```

Set `strategist_busy = true`. When the strategist's message arrives:
- Parse the JSON array
- Sort: `json_only=true` first, then by complexity ascending
- Deduplicate: discard any candidate whose `key` already exists in `strategy_definitions/`
- Push remaining to `pending[]`
- Set `strategist_busy = false`

### Dispatch: Builder

**Condition**: `!builder_busy && pending.length > 0`

Pop the first candidate from `pending[]`. Send (with `run_in_background: true`):

```
To: builder

Implement the following strategy:
<paste candidate JSON object>

STEPS:
If json_only == true:
  Write the JSON definition directly to strategy_definitions/<subfolder>/<key>.json.
  Use existing files in that subfolder as schema templates.

If json_only == false (new Python class needed):
  1. Read the most similar existing strategy file in strategies/ for patterns
  2. Read strategies/core.py for the base class interface
  3. Write the new Python class to strategies/<snake_case_name>.py
  4. Add the import and export to strategies/__init__.py
  5. Write the JSON definition to strategy_definitions/<subfolder>/<key>.json

RETURN FORMAT (plain text, one line):
Success: DONE: strategy_key=<key> | file=strategy_definitions/<path> | json_only=<true/false> | tunable_params=<value or null>
Failure: FAILED: strategy_key=<key> | reason=<brief description>

Send result via SendMessage to "orchestrator".
```

Set `builder_busy = true`. When builder's message arrives:
- If `DONE`: parse fields, push `{key, subfolder, json_only, tunable_params}` to `built[]`
- If `FAILED`: push `{key, reason}` to `skip_log[]`
- Set `builder_busy = false`

### Dispatch: Backtester

**Condition**: `backtester_count < 2 && built.length > 0`

Pop the first entry from `built[]`. Send (with `run_in_background: true`):

```
To: backtester

Run a backtest for: strategy_key=<key>

STEPS:
1. Run: python scripts/run_backtest.py --use-definitions --strategy <key>
2. If it fails: read the error, attempt one fix, retry once
3. Extract metrics from the output or from results/strategies/<key>/metrics.json

RETURN FORMAT (plain text, one line):
Success: OK: strategy_key=<key> | return=X.X% | sharpe=X.XX | maxdd=-X.X%
Failure: FAIL: strategy_key=<key> | error=<brief description>

Send result via SendMessage to "orchestrator".
```

Increment `backtester_count`. When backtester's message arrives:
- If `OK`: store metrics against the key, determine overfitting mode (see below), dispatch analyst immediately
- If `FAIL`: push `{key, reason}` to `skip_log[]`
- Decrement `backtester_count`

### Dispatch: Analyst

**Condition**: `analyst_count < 2` — triggered immediately after a successful backtester result (and re-checked each loop turn)

Determine overfitting mode from the `built[]` entry for this key:

| Condition | Mode |
|-----------|------|
| `json_only && subfolder in ["composed", "portfolios"]` | `skip` |
| `tunable_params` is not null | `params` (use the tunable_params value) |
| otherwise | `n1` |

Send (with `run_in_background: true`):

```
To: analyst

Run an overfitting check for: strategy_key=<key>
Mode: <skip|params|n1>
Params (if mode=params): <tunable_params value>

STEPS:
If mode == "skip":
  Return: SKIP: strategy_key=<key>

If mode == "params":
  Run: python scripts/run_overfitting.py --strategy <key> --param <params>

If mode == "n1":
  Run: python scripts/run_overfitting.py --strategy <key> --n-trials 1

Parse DSR and PBO from the output. Apply verdicts:
  PASS: DSR >= 0.95 and PBO <= 0.30
  WARN: DSR in [0.80, 0.95) or PBO in (0.30, 0.50]
  FAIL: DSR < 0.80 or PBO > 0.50

If the script errors: return ERROR with reason (do not skip reporting).

RETURN FORMAT (plain text, one line):
RESULT: strategy_key=<key> | dsr=X.XXX | dsr_verdict=PASS|WARN|FAIL | pbo=X.XX% | pbo_verdict=PASS|WARN|FAIL
SKIP: strategy_key=<key>
ERROR: strategy_key=<key> | reason=<brief>

Send result via SendMessage to "orchestrator".
```

Increment `analyst_count`. When analyst's message arrives:
- Push `{key, metrics, overfitting}` to `analyzed[]`
- Decrement `analyst_count`

### Report

When `analyzed[]` has entries, pop each and report:

```
✓ Built: [Strategy Name]
  File: strategy_definitions/[path]/[name].json
  Return: X% | Sharpe: X.XX | Max DD: -X%
  Overfitting: DSR=X.XXX [PASS/WARN/FAIL] | PBO=X.XX% [PASS/WARN/FAIL]   ← omit if skipped

Next: [what the pipeline is currently doing — e.g. "backtesting momentum_carry while researching next candidates..."]
```

Increment `strategy_count`. If `strategy_count % 3 == 0`:
> Suggest the user run `/backtest-all` and `/dashboard` to review all results.

**For JSON-only composed/portfolio strategies** where mode was `skip`, the analyst never runs. Report after the backtest succeeds (do not wait for analyst):
```
✓ Built: [Strategy Name]
  File: strategy_definitions/[path]/[name].json
  Return: X% | Sharpe: X.XX | Max DD: -X%
  Overfitting: N/A (composed/portfolio — single config)
```

---

## Stop / Cleanup

When the user says "stop", "pause", or "enough":

1. Finish any in-flight backtests — wait for all pending backtester messages if `backtester_count > 0`
2. Do not wait for strategist or builder (they are background)
3. Send shutdown signal to all agents:
   ```
   SendMessage("strategist",  "Shutdown: stop after current task.")
   SendMessage("builder",     "Shutdown: stop after current task.")
   SendMessage("backtester",  "Shutdown: stop after current task.")
   SendMessage("analyst",     "Shutdown: stop after current task.")
   ```
4. Call `TeamDelete(team_name="strategy-pipeline")`
5. Print session summary:
   ```
   Session complete. Built N strategies:
   - strategy_key: Sharpe=X.XX, DSR=X.XXX [PASS/WARN/FAIL]
   - ...

   Skipped M:
   - strategy_key: <reason>
   - ...
   ```

---

## Rules

- **Never place orders** — this is research only
- **Never duplicate** an existing strategy definition — always check what exists before adding to `pending[]`
- **One strategy at a time per stage** — the builder never holds two in-flight strategies simultaneously
- If a strategy requires assets not present in `strategy_definitions/assets/`, discard it at the pending stage
- Keep JSON definitions clean and consistent — use existing files in the same subfolder as schema templates
- If the user says "stop", "pause", or "enough" — stop the loop and run the cleanup sequence above

---

## JSON Schema Reference

**Allocation strategy**:
```json
{
  "type": "allocation",
  "class": "StrategyClassName",
  "name": "Human Readable Name",
  "description": "What it does",
  "parameters": { "param": "value" },
  "underlying": ["assets/vusa", "assets/ssln", "assets/sgln", "assets/iwrd"]
}
```
Use asset keys matching filenames in `strategy_definitions/assets/`.

**Composed (overlay applied to allocation)**:
```json
{
  "type": "composed",
  "name": "Human Readable Name",
  "description": "What it does",
  "overlay": {
    "class": "OverlayClassName",
    "parameters": { "param": "value" }
  },
  "underlying": "allocations/base_strategy"
}
```

**Portfolio (meta-allocation over multiple strategies)**:
```json
{
  "type": "portfolio",
  "class": "EqualWeightStrategy",
  "name": "Meta Portfolio Name",
  "description": "What it does",
  "underlying": ["composed/strategy_a", "composed/strategy_b"]
}
```
