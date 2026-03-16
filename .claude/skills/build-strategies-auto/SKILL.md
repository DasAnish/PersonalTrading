---
name: build-strategies-auto
description: Unattended strategy builder loop — researches and builds new trading strategies one at a time with no sub-agents and no approval prompts
---

# Strategy Builder Loop (Unattended)

You are running a continuous strategy research-and-build loop. You work on **one strategy at a time**, doing all research and implementation inline — **no sub-agents, no approval prompts**. Safe to run while the user is away.

---

## Context

**Assets available**: VUSA (S&P 500), SSLN (silver), SGLN (gold), IWRD (world equities) — all GBP-hedged UK ETFs.

**Existing strategy classes** (in `strategies/`):
- `HRPStrategy` — Hierarchical Risk Parity (`hrp.py`)
- `TrendFollowingStrategy` — EWMA momentum with vol scaling (`trend_following.py`)
- `EqualWeightStrategy` — equal weight allocation (`equal_weight.py`)
- `MinimumVarianceStrategy` — mean-variance optimisation (`minimum_variance.py`)
- `RiskParityStrategy` — equal marginal risk contribution (`risk_parity.py`)
- `MomentumStrategy` — top-N momentum selection (`momentum.py`)
- Overlays: `VolatilityTargetStrategy`, `ConstraintStrategy`, `LeverageStrategy` (`overlays.py`)

**Existing strategy definitions** (in `strategy_definitions/`):
- `allocations/`: equal_weight, hrp_single, hrp_ward, trend_following, minimum_variance, risk_parity, momentum_top2
- `composed/`: hrp_15vol, hrp_30vol, trend_15vol, trend_30vol, hrp_with_constraints, trend_with_vol_12, trend_constrained_vol_target
- `portfolios/`: meta_trend_hrp_15vol, meta_trend_hrp_30vol, meta_multi_volatility
- `overlays/`: vol_target_12/15/30pct, constraints_5_40, constraints_10_30

**Architecture rules**:
- `AllocationStrategy`: calculates weights across a list of assets — implements `calculate_weights(context)`
- `OverlayStrategy`: transforms weights from an underlying strategy
- JSON-only strategies: no Python needed, just a new file in `strategy_definitions/`
- JSON definitions use `"underlying"` arrays referencing other definition paths (e.g. `"assets/vusa"`)

---

## Loop Procedure

Repeat the following loop indefinitely until the user stops you:

### Step 1 — Survey what exists

Read all JSON files in `strategy_definitions/` (allocations/, composed/, portfolios/, overlays/) to get the current full picture of what is already implemented. Do this at the start of every loop iteration so you never duplicate.

### Step 2 — Select the next strategy to build

Based on what you've read plus your knowledge of systematic trading approaches, pick one new strategy not yet implemented. Work through this priority order:

**Priority 1 — JSON-only compositions** (no Python needed):
- New parameter variants of existing allocations (e.g. momentum with top_n=3, trend with shorter lookback 252d, HRP with average linkage)
- New overlay combinations not yet composed (e.g. minimum_variance + vol target, risk_parity + constraints)
- New meta-portfolios combining existing composed strategies in new groupings

**Priority 2 — New Python allocation classes** (only when JSON-only options are exhausted):
- Dual Momentum (absolute + relative momentum filter)
- Protective Asset Allocation (trend filter as safe-asset switch)
- Adaptive Asset Allocation (momentum ranking + minimum variance)
- Mean reversion / carry

Tell the user: "Building: **[Strategy Name]** — [one sentence description]"

### Step 3 — Implement

**If JSON-only**:
- Write the JSON file directly to the correct `strategy_definitions/` subfolder
- Use existing files as schema templates
- Name the file with a clear slug (e.g. `momentum_top3.json`, `min_var_15vol.json`)

**If new Python class needed**:
1. Read the most relevant existing strategy file for patterns (e.g. `strategies/momentum.py`)
2. Read `strategies/base.py` for the base class interface
3. Write the new class to `strategies/<name>.py`
4. Read `strategies/__init__.py` and add the import and registry entry
5. Write the JSON definition to `strategy_definitions/allocations/<name>.json`

### Step 4 — Validate

Run the backtest:
```
python scripts/run_backtest.py --strategy <slug_name>
```

- **Success**: note the key metrics from stdout (total return, Sharpe, max drawdown)
- **Failure**: read the error, fix it, run once more. If it fails again, skip this strategy, log the reason, and continue the loop.

### Step 5 — Report and loop

Print:
```
✓ Built: [Strategy Name]
  File: strategy_definitions/[path]/[name].json
  Return: X% | Sharpe: X.XX | Max DD: -X%

Next: researching the next strategy...
```

Then immediately go back to Step 1.

After every 3 strategies built, also print:
```
--- 3 strategies built. Run /backtest-all and /dashboard to review results. ---
```

---

## Rules

- **One strategy at a time** — complete or skip before moving to the next
- **Never place orders** — research only
- **Never duplicate** — always re-read `strategy_definitions/` at the start of each iteration
- **Only use VUSA, SSLN, SGLN, IWRD** — skip any idea that needs other assets
- **No sub-agents** — do all work inline; this is the unattended version
- Stop immediately if the user says "stop", "pause", or "enough" and summarise what was built this session

---

## JSON Schema Reference

**Allocation** (`strategy_definitions/allocations/`):
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

**Composed** (`strategy_definitions/composed/`):
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

**Portfolio** (`strategy_definitions/portfolios/`):
```json
{
  "type": "portfolio",
  "class": "EqualWeightStrategy",
  "name": "Meta Portfolio Name",
  "description": "What it does",
  "underlying": ["composed/strategy_a", "composed/strategy_b"]
}
```
