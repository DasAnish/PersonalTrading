---
name: build-strategies-auto
description: Unattended strategy builder loop — researches and builds new trading strategies one at a time with no sub-agents and no approval prompts
---

# Strategy Builder Loop (Unattended)

You are running a continuous strategy research-and-build loop. You work on **one strategy at a time**, doing all research and implementation inline — **no sub-agents, no approval prompts**. Safe to run while the user is away.

---

## Context

**Assets available**: Read dynamically from `strategy_definitions/assets/` — each `.json` file in that folder is an investable asset. Read this folder at the start of every loop iteration to discover the current asset universe. Do not hardcode asset lists.

Current universe (as of last update, 30 assets — always re-read `strategy_definitions/universe.json` for the live list): VUSA (S&P 500), SSLN (physical silver ETC), SGLN (physical gold ETC), IWRD (MSCI World), EQQQ (NASDAQ-100), COMM/COMML (diversified commodities), AIGC (broad commodities ETC), IIND (MSCI India), IMEU (MSCI Europe), WCOA (enhanced/broad commodities), VUTY (US Treasury bonds), BRNT (Brent crude oil), CRUD (WTI crude oil), plus 17 more spanning bonds (HYLD, AGGU, SEGA, TIGG), European/EM/thematic equity (ASHR, SAEM, CACX, CSX5, IEMU, WCLD, WSML, AWESGS, EMMCHA, EXXW, EXX5, EXI2, EXSA).

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
- JSON-only strategies: no Python needed, just a new file in `strategy_definitions/`
- JSON definitions use `"underlying"` arrays referencing other definition paths (e.g. `"assets/vusa"`)

**Combining assets / sub-selecting the universe**: `strategy_definitions/universe.json`
groups assets by `equity`, `bond`, `commodity`, `europe_equity`, `em_equity`, and
`all`. The loader resolves `"underlying": "universe:<group>"` at load time, so a
strategy pointed at a group automatically picks up assets added to that group
later — never hand-copy a group's asset list into a new definition.
- Whole group: `"underlying": "universe:bond"`.
- Multiple groups, order-independent: `"underlying": ["universe:equity", "universe:commodity"]`.
- Order-sensitive (e.g. `ProtectiveAssetAllocationStrategy` treats the last
  resolved asset as the single safe asset): put group refs first, fixed asset(s)
  last — `"underlying": ["universe:equity", "universe:commodity", "assets/vuty"]`.
  Never point a position-sensitive class straight at `"universe:all"`.
- Bespoke basket not matching a named group (e.g. a "growth theme" cutting
  across classes): list individual `"assets/<key>"` refs explicitly, as
  `allocations/hrp_growth_theme.json` does — and if it looks reusable, add it
  as a new named group in `universe.json` instead of repeating the list.

---

## Loop Procedure

Repeat the following loop indefinitely until the user stops you:

### Step 1 — Survey what exists

Read all JSON files in `strategy_definitions/` — including `assets/`, `allocations/`, `composed/`, `portfolios/`, `overlays/` — to get the current full picture of what is already implemented and which assets are available. Do this at the start of every loop iteration so you never duplicate or reference an asset that doesn't exist.

### Step 2 — Select the next strategy to build

First, read `research/backlog.md`. If any idea has `status: new`, read the full idea
file in `research/ideas/<slug>.md` (pre-registered hypothesis + rule sketch) and
prefer building that idea next — set `research_ref` to the idea's filename slug
(without `.md`) and `mechanism` to its frontmatter `mechanism` tag for use in Step 5.

If the backlog has no `status: new` idea, read `results/mechanism_coverage.json`
(if present) and prefer a mechanism with a LOW count over an already-saturated one
(e.g. mean-reversion/vol-premium/carry/seasonality tend to be underrepresented vs.
trend/diversification/meta). Tag the strategy you build with a `mechanism` from the
fixed vocabulary — trend, momentum-cs, mean-reversion, carry, vol-premium,
diversification, regime, hedging-overlay, seasonality, meta — even when it isn't
derived from a backlog idea.

Only fall back to the priority order below when no backlog idea and no clear
underrepresented-mechanism candidate is feasible:

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

### Step 4b — Overfitting Check

Run **immediately after a successful validate**. Skip if the strategy type is composed/portfolio (JSON-only compositions with N=1 trivially pass).

For allocation strategies with tunable parameters, use the param-sweep mode
(answers a different question, PBO stability across a param grid,
that the single-config battery below doesn't cover):
```bash
# Examples:
python scripts/run_all_overfitting.py --strategy hrp --param linkage_method=single,complete,ward
python scripts/run_all_overfitting.py --strategy momentum --param top_n=1,2,3
python scripts/run_all_overfitting.py --strategy trend_following --param lookback_days=126,252,504
```
Note the DSR and PBO verdict for the report.

For allocation strategies WITHOUT tunable params, run the validation battery
(replaces the old bare `--n-trials 1` DSR check):
```bash
python scripts/validate_strategy.py --strategy <strategy_key> --json
```
The last stdout line is single-line JSON:
`{"strategy_key":..., "generated":..., "tests":[{name,verdict,values,note} x4], "overall":"PASS|WARN|FAIL"}`
(tests named `dsr`, `minbtl`, `cpcv`, `bootstrap`). Extract `overall`, the `minbtl`
verdict, `tests[dsr].values.dsr` + verdict, `tests[cpcv].values.prob_oos_sharpe_positive`,
and `tests[bootstrap].values.sharpe_pct5` for the report.

If either script errors, log and skip this step.

### Step 5 — Report and loop

Print (use the `params` line if Step 4b ran the param sweep, the `battery` line if
it ran the validation battery):
```
✓ Built: [Strategy Name]
  File: strategy_definitions/[path]/[name].json
  Return: X% | Sharpe: X.XX | Max DD: -X%
  Overfitting: DSR=X.XXX [PASS/WARN/FAIL] | PBO=X.XX% [PASS/WARN/FAIL]                          ← params mode
  Overfitting: [PASS/WARN/FAIL] overall | MinBTL=[verdict] DSR=X.XXX/[verdict] CPCV_p=X.XX Boot_p5=X.XXX  ← battery mode

Next: researching the next strategy...
```

If this strategy carries a `research_ref` (Step 2), update that idea's frontmatter
`status` in `research/ideas/<research_ref>.md` and the matching row in
`research/backlog.md`: `built` (backtest succeeded), then `validated` when the
overfitting verdict is PASS/WARN or `rejected` when it is FAIL. Leave it at `built`
if Step 4b was skipped (composed/portfolio, no verdict available).

Then immediately go back to Step 1.

After every 3 strategies built, also print:
```
--- 3 strategies built. Run /backtest-all and /dashboard to review results. ---
```

After every 5 strategies built, also print:
```
--- 5 strategies built. Run `python scripts/run_all_overfitting.py --spa` for a
library-wide multiple-testing check (White's Reality Check / Hansen's SPA) — this
corrects for the growing number of strategies tried across the whole session. ---
```

---

## Rules

- **One strategy at a time** — complete or skip before moving to the next
- **Never place orders** — research only
- **Never duplicate** — always re-read `strategy_definitions/` at the start of each iteration
- **Only use assets present in `strategy_definitions/assets/`** — skip any idea that needs assets not in that folder
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
Use asset keys matching filenames in `strategy_definitions/assets/` (e.g. `"assets/eqqq"`, `"assets/vuty"`), or a universe group reference in place of a hand-written list — see "Combining assets / sub-selecting the universe" above:
```json
"underlying": "universe:bond"
```
or a mix of group refs and fixed assets, order preserved:
```json
"underlying": ["universe:equity", "universe:commodity", "assets/vuty"]
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
