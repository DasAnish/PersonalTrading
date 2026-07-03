# Overfitting Analysis

Tools for detecting whether a strategy's backtest performance is likely to
persist out-of-sample, or is the result of chance and data mining.

---

## Three Metrics

### 1. DSR — Deflated Sharpe Ratio
**What it answers:** "Is my observed Sharpe ratio real, or is it inflated by
testing many parameter combinations?"

When you run N backtests and pick the best one, the winner looks good partly by
luck. DSR corrects for this selection bias by raising the Sharpe hurdle in
proportion to N. It returns a probability in [0, 1]:

| Score | Verdict | Meaning |
|-------|---------|---------|
| ≥ 0.95 | PASS | Sharpe is very likely genuine |
| ≥ 0.80 | WARN | Moderate confidence |
| < 0.80 | FAIL | Result may be a statistical artefact |

**Works for:** any single strategy, even with N=1 (conservative but valid).

**Reference:** Bailey & López de Prado (2014), *The Deflated Sharpe Ratio*.

---

### 2. PBO — Probability of Backtest Overfitting
**What it answers:** "If I pick the best parameter configuration in-sample,
how often does it underperform out-of-sample?"

Uses Combinatorially Symmetric Cross-Validation (CSCV): splits the data into
S equal time chunks, creates C(S, S/2) IS/OOS splits, and asks in each whether
the IS-best configuration beats the OOS median. PBO = fraction of splits where
it doesn't.

| Score | Verdict | Meaning |
|-------|---------|---------|
| ≤ 0.30 | PASS | IS-best config usually holds OOS |
| ≤ 0.50 | WARN | Moderate overfitting risk |
| > 0.50 | FAIL | IS winner likely to fail OOS |

**Requires:** a return matrix with ≥ 2 parameter configurations (T × N).
With only 1 configuration PBO degenerates — use DSR or k-fold instead.

**Reference:** Bailey et al. (2014), *The Probability of Backtest Overfitting*.

---

### 3. K-Fold Temporal Stability
**What it answers:** "Does this strategy work consistently in every time period,
or is its performance concentrated in one lucky era?"

Splits the return series into k equal consecutive windows (default k=10) and
computes the annualised Sharpe ratio for each. Reports the fraction of folds
with positive Sharpe (`fraction_positive`).

| Score | Verdict | Meaning |
|-------|---------|---------|
| ≥ 0.70 | PASS | Positive Sharpe in 7+ of 10 folds |
| ≥ 0.50 | WARN | Positive in only 5-6 folds |
| < 0.50 | FAIL | Fails more than half the folds |

**Works for:** any single strategy regardless of parameter count.
Requires ≥ `k * 3` return periods (at least 3 data points per fold).

---

## Implementation

| Symbol | Location |
|--------|----------|
| `DSRResult` dataclass | [analytics/overfitting.py](../analytics/overfitting.py) |
| `PBOResult` dataclass | [analytics/overfitting.py](../analytics/overfitting.py) |
| `KFoldResult` dataclass | [analytics/overfitting.py](../analytics/overfitting.py) |
| `calculate_deflated_sharpe_ratio()` | [analytics/overfitting.py](../analytics/overfitting.py) |
| `calculate_pbo()` | [analytics/overfitting.py](../analytics/overfitting.py) |
| `calculate_kfold_stability()` | [analytics/overfitting.py](../analytics/overfitting.py) |
| `run_overfitting_analysis()` | [analytics/overfitting.py](../analytics/overfitting.py) |
| `overfitting_analysis_to_dict()` | [analytics/overfitting.py](../analytics/overfitting.py) |

---

## Scripts

### Single strategy (DSR + k-fold + optional PBO sweep)
```bash
# Mode 1: parameter sweep → DSR + PBO + k-fold
python scripts/run_overfitting.py \
    --strategy hrp \
    --param linkage_method=single,complete,ward

# Mode 2: DSR + k-fold from existing backtest results
python scripts/run_overfitting.py --strategy hrp_ward --n-trials 4
```

### Batch: all 82+ strategies
```bash
# Fast: DSR + k-fold only (~30 seconds)
python scripts/run_all_overfitting.py --skip-pbo

# Single strategy
python scripts/run_all_overfitting.py --strategy hrp_ward --skip-pbo

# Full: includes PBO sweeps for base strategy families (~10 minutes)
python scripts/run_all_overfitting.py

# Custom fold count
python scripts/run_all_overfitting.py --skip-pbo --n-folds 5
```

Results are saved to `results/strategies/<strategy_key>/overfitting_analysis.json`.

---

## Output Format

`overfitting_analysis.json` schema:
```json
{
  "strategy_key": "hrp_ward",
  "analysis_date": "2026-03-17T...",
  "n_param_combinations": 4,
  "config": { "param_grid": {}, "periods_per_year": 12, "s_subsets": 16, "n_folds": 10 },
  "errors": [],
  "dsr": {
    "dsr": 0.9982,
    "observed_sharpe": 1.45,
    "sharpe_reference": 0.21,
    "n_trials": 4,
    "t_periods": 77,
    "skewness": -0.32,
    "excess_kurtosis": 0.14,
    "verdict": "PASS",
    "threshold_pass": 0.95,
    "threshold_warn": 0.80
  },
  "pbo": null,
  "kfold": {
    "n_folds": 10,
    "fold_sharpes": [1.2, 0.8, 1.5, -0.3, 1.1, 0.9, 1.4, 0.7, 1.3, 1.0],
    "mean_sharpe": 0.96,
    "std_sharpe": 0.52,
    "fraction_positive": 0.9,
    "worst_fold_sharpe": -0.3,
    "verdict": "PASS",
    "threshold_pass": 0.70,
    "threshold_warn": 0.50
  }
}
```

---

## Tests

```bash
python -m pytest tests/test_overfitting.py -v
```

49 tests covering DSR, PBO, k-fold, parameter sweep integration, serialisation,
and end-to-end `run_overfitting_analysis()` flows.

---

## When to Use Each

| Scenario | Use |
|----------|-----|
| Any single strategy, quick check | DSR + k-fold |
| Strategy with parameter grid (linkage, lookback, top-N) | DSR + PBO + k-fold |
| All strategies at once | `run_all_overfitting.py --skip-pbo` |
| Deep investigation of a strategy family | `run_overfitting.py --strategy hrp --param linkage_method=...` |

---

## Extended methods (2026)

Beyond DSR, PBO (CSCV) and k-fold, the analysis now includes:

| Method | Module | Verdict basis |
|--------|--------|---------------|
| **MinBTL** (Minimum Backtest Length) | `analytics/overfitting.py::calculate_minbtl` | PASS if `actual_years ≥ min_years` (Bailey/López de Prado 2014). Simplified MinTRL form (no skew/kurtosis correction). |
| **Purged k-fold** (embargo) | `calculate_kfold_stability(..., embargo_periods)` | `embargo_periods=0` reproduces classic k-fold; `--embargo-days` converts at monthly cadence. |
| **Walk-forward ratio** | `analytics/overfitting_results.py::walk_forward_to_dict` | PASS `<1.5x`, WARN `<2.5x`, else FAIL (avg IS / avg OOS). `--walk-forward`. |
| **CPCV** | `analytics/cpcv.py::CPCVEngine` | OOS Sharpe distribution over all `C(k,2)` test-group combinations; PASS if `P(Sharpe>0) ≥ 0.9` and 5th pct `> −0.5`. `--method cpcv --cpcv-folds`. |
| **Block bootstrap** | `analytics/bootstrap.py::BlockBootstrap` | Stationary (Politis–Romano) resampling → Sharpe/Calmar/maxDD/annual distributions. `--method bootstrap --bootstrap-n --block-months [--bootstrap-fast]`. |
| **White's RC / Hansen's SPA** | `analytics/spa.py::compute_spa` | Data-snooping p-values across the whole library vs `equal_weight`. Small p rejects "no strategy beats the benchmark". `--spa` (batch). |

### New CLI flags

```bash
# Per-strategy (run_overfitting.py)
python scripts/run_overfitting.py --strategy hrp_single --method cpcv --cpcv-folds 6 --embargo-days 10
python scripts/run_overfitting.py --strategy hrp_single --method bootstrap --bootstrap-fast
python scripts/run_overfitting.py --strategy hrp_single --n-trials 20 --scenario-removal

# Batch (run_all_overfitting.py)
python scripts/run_all_overfitting.py --walk-forward --composed-pbo --spa
```

### Output schema additions

`overfitting_analysis.json` gains optional top-level keys (all `null` when not
computed, so readers/dashboard tolerate absence): `minbtl`, `walkforward`,
`cpcv`, `bootstrap`, `spa`. The batch `--spa` run also writes
`results/spa_analysis.json`. Non-finite metric values (inf/NaN) serialize to
`null` so the JSON stays strictly valid.

### Scenario removal (stress testing)

`stress_test.json` carries `scenario_removal` (leave-one-crisis-out) with both
Sharpe and Calmar deltas and a `scenario_removal_mode` of `excise` (re-slice the
value series) or `rerun` (drop each crisis window from prices and re-run the
backtest). Flags: `--scenario-removal` on `run_backtest.py` (rerun) and
`run_overfitting.py` (excise).
