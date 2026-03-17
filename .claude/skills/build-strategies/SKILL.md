---
name: build-strategies
description: Research, design, and build new trading strategies one at a time in a continuous loop using sub-agents
---

# Strategy Builder Loop

You are running a continuous strategy research-and-build loop. You work on **one strategy at a time**, using sub-agents to parallelise research and implementation where possible.

---

## Context

**Assets available**: Read dynamically from `strategy_definitions/assets/` — each `.json` file in that folder is an investable asset. The Research sub-agent must read this folder at the start of every loop iteration to discover the current asset universe. Do not hardcode asset lists.

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

## Loop Procedure

Repeat the following loop indefinitely until the user stops you:

### Step 1 — Research (spawn a Research sub-agent)

Spawn a **general-purpose sub-agent** with `model: "haiku"` and **`mode: "bypassPermissions"`** to do the following research in parallel:
1. Read all files in `strategy_definitions/` to understand what already exists — **including `strategy_definitions/assets/` to discover the current asset universe**
2. Read `docs/strategies.md` for architecture context
3. Search for ideas from well-known systematic trading approaches:
   - Dual Momentum (absolute + relative momentum)
   - Protective Asset Allocation (trend + momentum hybrid)
   - Adaptive Asset Allocation (rolling momentum + minimum variance)
   - Mean reversion / carry strategies
   - Multi-factor combinations
   - New overlay compositions (different vol targets, lookback params, constraint combos)
   - Meta-portfolio combinations of existing strategies
4. Return a **ranked shortlist of 3 candidate strategies** not yet implemented, with:
   - Name and description
   - Which existing classes it reuses vs. needs new Python code
   - Whether it can be done via JSON only or needs new Python
   - Estimated implementation complexity (Low/Medium/High)

### Step 2 — Select

Pick the **top candidate** from the research agent's shortlist — favour:
1. JSON-only strategies (no new Python needed) first
2. Strategies that reuse existing classes with different parameters
3. Novel allocation algorithms only when all JSON-only options are exhausted

Tell the user: "Building: **[Strategy Name]** — [one sentence description]"

### Step 3 — Implement (spawn an Implementation sub-agent if new Python is needed)

**If JSON-only**: Write the JSON definition directly in `strategy_definitions/` — no sub-agent needed.

**If new Python class needed**: Spawn a **general-purpose sub-agent** with `model: "haiku"` and **`mode: "bypassPermissions"`** to:
1. Read the relevant existing strategy file(s) for reference patterns
2. Read `strategies/core.py` and `strategies/base.py` for the base class interface
3. Write the new Python class in `strategies/`
4. Register it in `strategies/__init__.py`
5. Return the completed code

Then write the JSON definition yourself after the sub-agent completes.

### Step 4 — Validate

Run: `python scripts/run_backtest.py --strategy <strategy_name>`

- If it succeeds: report the key metrics (total return, Sharpe, max drawdown)
- If it fails: read the error, fix it, and retry once. If it fails again, skip this strategy and log the issue, then continue the loop.

### Step 4b — Overfitting Check

Run this **immediately after a successful validate**, before reporting results.

**Determine what to run based on strategy type**:

- **JSON-only composed/portfolio strategies**: Skip overfitting check (N=1 trivially passes DSR; PBO requires multiple configs).
- **Allocation strategies with a primary tunable parameter** (e.g. `linkage_method`, `lookback_days`, `top_n`): Run with at least 3 variants.
- **New Python allocation class**: Run with 3 parameter variants if any exist, else skip.

```bash
# Example: new HRP variant
python scripts/run_overfitting.py --strategy hrp --param linkage_method=single,complete,ward

# Example: new momentum variant
python scripts/run_overfitting.py --strategy momentum --param top_n=1,2,3

# Example: no tunable params (use Mode 2 with N=1)
python scripts/run_overfitting.py --strategy <strategy_key> --n-trials 1
```

**Interpret the result**:
- **PASS** (DSR ≥ 0.95 and PBO ≤ 0.30): proceed to Step 5 normally.
- **WARN** (DSR in [0.80, 0.95) or PBO in (0.30, 0.50]): proceed to Step 5 but include the warning in the report.
- **FAIL** (DSR < 0.80 or PBO > 0.50): proceed to Step 5 but flag the strategy as **high risk of overfitting**. Do not skip — the strategy may still be valid, but the user should know.

If `run_overfitting.py` errors (e.g. import error, insufficient data): log the error, skip Step 4b, and proceed to Step 5.

### Step 5 — Report

Tell the user:
```
✓ Built: [Strategy Name]
  File: strategy_definitions/[path]/[name].json
  Return: X% | Sharpe: X.XX | Max DD: -X%
  Overfitting: DSR=X.XXX [PASS/WARN/FAIL] | PBO=X.XX% [PASS/WARN/FAIL]   ← include if Step 4b was run

Next: researching the next strategy...
```

Then immediately return to Step 1.

---

## Rules

- **One strategy at a time** — never start a new strategy until the current one is complete or explicitly skipped
- **Never place orders** — this is research only
- **Never duplicate** an existing strategy definition — always check what exists first
- If the user says "stop", "pause", or "enough", stop the loop immediately and summarise what was built
- If a strategy requires data or assets not present in `strategy_definitions/assets/`, skip it
- Keep JSON definitions clean and consistent with existing schema — use the existing files as templates
- After every 3 strategies built, suggest the user run `/backtest-all` and `/dashboard` to review results

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
Use asset keys matching filenames in `strategy_definitions/assets/` (e.g. `"assets/eqqq"`, `"assets/vuty"`).

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
