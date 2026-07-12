"""
Batch-analysis logic for ``scripts/run_all_overfitting.py``.

Holds the library-wide helpers: n-trials estimation, the DSR + k-fold batch,
PBO parameter sweeps (+ optional walk-forward), and White's Reality
Check / Hansen's SPA. Shared IO/reporting helpers live in the sibling
``overfitting_lib`` module.

Nothing here hard-codes a periods-per-year (252/12): the annualisation factor
is always inferred from the return-series spacing via
``analytics.metrics.infer_periods_per_year``.
"""

import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

# Project root + scripts dir on path so both top-level packages and the
# sibling ``backtest_lib.overfitting_lib`` resolve regardless of how this
# module is imported.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_SCRIPTS_DIR))

from analytics.metrics import infer_periods_per_year  # noqa: E402
from analytics.overfitting import (  # noqa: E402
    calculate_deflated_sharpe_ratio,
    calculate_minbtl,
    run_overfitting_analysis,
)
from analytics.overfitting_results import build_walk_forward_result  # noqa: E402
from backtesting.results_schema import OVERFITTING_FILE  # noqa: E402
from backtesting.results_schema import strategy_dir as schema_strategy_dir  # noqa: E402
from data import HistoricalDataCache, align_dataframes  # noqa: E402
from optimization import ParameterSweep, WalkForwardAnalysis  # noqa: E402
from strategies import (  # noqa: E402
    AssetStrategy,
    HRPStrategy,
    TrendFollowingStrategy,
    EqualWeightStrategy,
    MinimumVarianceStrategy,
    RiskParityStrategy,
    MomentumTopNStrategy,
)
from strategies.strategy_loader import StrategyLoader  # noqa: E402

from backtest_lib.overfitting_lib import (  # noqa: E402
    CURRENCY,
    RESULTS_DIR,
    SYMBOLS,
    load_portfolio_history,
    save_analysis,
)

logger = logging.getLogger(__name__)

# Parameter grids for PBO sweeps per base strategy family
PBO_PARAM_GRIDS: Dict[str, dict] = {
    "hrp": {
        "strategy_class": HRPStrategy,
        "param_grid": {"linkage_method": ["single", "complete", "average", "ward"]},
    },
    "trend_following": {
        "strategy_class": TrendFollowingStrategy,
        "param_grid": {
            "lookback_days": [126, 252, 504],
            "half_life_days": [30, 60, 90],
        },
    },
    "momentum": {
        "strategy_class": MomentumTopNStrategy,
        "param_grid": {"top_n": [1, 2, 3], "lookback_days": [126, 252]},
    },
    "minimum_variance": {
        "strategy_class": MinimumVarianceStrategy,
        "param_grid": {"lookback_days": [126, 252, 504]},
    },
    "risk_parity": {
        "strategy_class": RiskParityStrategy,
        "param_grid": {"lookback_days": [126, 252, 504]},
    },
    "equal_weight": {
        "strategy_class": EqualWeightStrategy,
        "param_grid": {"rebalance_threshold": [0.0, 0.02, 0.05]},
    },
}


def _load_class_lookup(strategy_keys: List[str]) -> Dict[str, str]:
    """
    Map each strategy_key -> its definition's ``class`` field, via
    ``StrategyLoader``. Keys whose definition can't be loaded map to
    themselves (forming a singleton class), so they don't crash the batch
    or get incorrectly grouped with an unrelated family.
    """
    loader = StrategyLoader()
    lookup: Dict[str, str] = {}
    for key in strategy_keys:
        try:
            definition = loader.load_definition(key)
            lookup[key] = definition.get("class") or key
        except Exception as exc:
            logger.warning(
                "Could not load definition for %s (%s); treating as its own class.",
                key,
                exc,
            )
            lookup[key] = key
    return lookup


def build_n_trials_map(
    strategy_keys: List[str],
    class_lookup: Optional[Dict[str, str]] = None,
) -> Dict[str, int]:
    """
    Estimate n_trials (N) for DSR / MinBTL per strategy key.

    Two-tier logic (fixes the old bug of lumping trend_following,
    trend_signal_rp, trend_signal_mvo together just because they share a
    "trend" prefix token — they are different strategy classes):

    (a) If a strategy's key matches a ``PBO_PARAM_GRIDS`` family (by prefix)
        AND its definition ``class`` equals that family's
        ``strategy_class``, n_trials = the cartesian product size of that
        family's grid — the TRUE number of configurations swept.
    (b) Otherwise, group by the definition's ``class`` field and count real
        siblings sharing that class.

    Floors n_trials at 2 (DSR/MinBTL require N >= 2).

    Parameters
    ----------
    class_lookup : dict, optional
        strategy_key -> definition class name. If None (production
        default), loaded via ``_load_class_lookup``. Tests pass a
        synthetic dict directly to avoid touching the filesystem.
    """
    if class_lookup is None:
        class_lookup = _load_class_lookup(strategy_keys)

    n_trials_map: Dict[str, int] = {}
    remaining: List[str] = []

    for key in strategy_keys:
        family = None
        for fam, cfg in PBO_PARAM_GRIDS.items():
            if key != fam and not key.startswith(fam + "_"):
                continue
            if class_lookup.get(key) == cfg["strategy_class"].__name__:
                family = fam
                break
        if family is not None:
            grid = PBO_PARAM_GRIDS[family]["param_grid"]
            n = 1
            for values in grid.values():
                n *= len(values)
            n_trials_map[key] = max(n, 2)
        else:
            remaining.append(key)

    class_counts = Counter(class_lookup.get(k, k) for k in remaining)
    for key in remaining:
        n_trials_map[key] = max(class_counts[class_lookup.get(key, key)], 2)

    return n_trials_map


def run_dsr_kfold_batch(
    strategy_keys: List[str],
    n_folds: int,
    n_trials_map: Dict[str, int],
    embargo_days: int = 0,
) -> List[dict]:
    """Run DSR + k-fold (+ MinBTL) for every strategy. Returns summary rows."""
    summary_rows = []

    for key in strategy_keys:
        total_values = load_portfolio_history(key)
        if total_values is None:
            logger.warning("No portfolio_history.json for %s — skipping.", key)
            continue

        returns = total_values.pct_change().dropna()
        n_trials = n_trials_map.get(key, 2)

        # Infer periods_per_year and embargo_periods from the loaded data
        ppy = infer_periods_per_year(total_values.index)
        embargo_periods_key = round(embargo_days * ppy / 365.25) if embargo_days else 0

        analysis = run_overfitting_analysis(
            strategy_key=key,
            strategy_returns=returns,
            return_matrix=None,
            param_grid={},
            periods_per_year=ppy,
            n_folds=n_folds,
            embargo_periods=embargo_periods_key,
        )

        # Override n_trials to the honest family/class-based estimate for
        # DSR and MinBTL (run_overfitting_analysis defaults to N=2 when no
        # return_matrix is supplied, since it has no other way to know how
        # many configurations were actually explored for this key).
        if analysis.dsr is not None:
            analysis.dsr = calculate_deflated_sharpe_ratio(
                returns=returns,
                n_trials=n_trials,
                periods_per_year=ppy,
            )
            analysis.n_param_combinations = n_trials
        if analysis.minbtl is not None:
            analysis.minbtl = calculate_minbtl(
                observed_sharpe_annualized=(
                    analysis.dsr.observed_sharpe
                    if analysis.dsr
                    else analysis.minbtl.observed_sharpe
                ),
                n_trials=n_trials,
                actual_years=analysis.minbtl.actual_years,
            )

        save_analysis(analysis, key)

        dsr_val = f"{analysis.dsr.dsr:.4f}" if analysis.dsr else "N/A"
        dsr_v = analysis.dsr.verdict if analysis.dsr else "N/A"
        kf_frac = f"{analysis.kfold.fraction_positive:.0%}" if analysis.kfold else "N/A"
        kf_v = analysis.kfold.verdict if analysis.kfold else "N/A"

        # Overall verdict
        verdicts = []
        if analysis.dsr:
            verdicts.append(analysis.dsr.verdict)
        if analysis.kfold:
            verdicts.append(analysis.kfold.verdict)
        if all(v == "PASS" for v in verdicts):
            overall = "PASS"
        elif any(v == "FAIL" for v in verdicts):
            overall = "FAIL"
        else:
            overall = "WARN" if verdicts else "N/A"

        summary_rows.append(
            {
                "strategy": key,
                "n_trials": n_trials,
                "dsr": dsr_val,
                "dsr_verdict": dsr_v,
                "kfold_frac_pos": kf_frac,
                "kfold_verdict": kf_v,
                "overall": overall,
            }
        )

    return summary_rows


def run_pbo_sweeps(
    n_folds: int,
    embargo_days: int = 0,
    walk_forward: bool = False,
) -> List[dict]:
    """
    Run full PBO sweeps for base strategy families.

    If ``walk_forward`` is True, also runs ``WalkForwardAnalysis`` on the
    same ``strategy_class``/``param_grid``/``underlying``/``prices`` already
    loaded for the PBO sweep, and attaches the result as the ``walkforward``
    section of that family's overfitting_analysis.json.
    """
    cache = HistoricalDataCache(cache_dir="data/cache")
    data_dict = {}
    for symbol in SYMBOLS:
        # Offline analysis: whatever history the cache has is what we sweep.
        # (The strict range-covering lookup missed everything once the cache
        # start drifted past 2015-01-01 — see load_best_cached_data.)
        df = cache.load_best_cached_data(symbol)
        if not df.empty:
            data_dict[symbol] = df
    if not data_dict:
        print("ERROR: No cached price data. Run: python scripts/run_backtest.py --all")
        return []

    prices = align_dataframes(data_dict)
    underlying = [AssetStrategy(s, currency=CURRENCY) for s in SYMBOLS]
    lookback = 252
    backtest_start = prices.index[lookback]
    backtest_end = prices.index[-1]

    pbo_rows = []
    for family, cfg in PBO_PARAM_GRIDS.items():
        print(f"  PBO sweep: {family} ...")
        strategy_class = cfg["strategy_class"]
        param_grid = cfg["param_grid"]

        sweep = ParameterSweep(
            strategy_class=strategy_class,
            param_grid=param_grid,
            metric="sharpe_ratio",
            initial_capital=10_000.0,
            transaction_cost_bps=7.5,
            store_returns=True,
        )
        sweep_df = sweep.run(
            underlying=underlying,
            prices=prices,
            start_date=backtest_start,
            end_date=backtest_end,
            lookback_days=lookback,
        )
        if sweep_df.empty:
            print(f"  WARNING: Sweep returned no results for {family}.")
            continue

        return_matrix = sweep.get_return_matrix()
        best_key = next(iter(sweep.return_series_))
        best_values = sweep.return_series_[best_key]
        best_returns = best_values.pct_change().dropna()

        # Infer periods_per_year and embargo_periods from the sweep data
        ppy = infer_periods_per_year(best_values.index)
        embargo_periods_sweep = (
            round(embargo_days * ppy / 365.25) if embargo_days else 0
        )

        analysis = run_overfitting_analysis(
            strategy_key=f"{family}__pbo_sweep",
            strategy_returns=best_returns,
            return_matrix=return_matrix,
            param_grid=param_grid,
            periods_per_year=ppy,
            n_folds=n_folds,
            embargo_periods=embargo_periods_sweep,
        )

        wf_val = "N/A"
        wf_v = "N/A"
        if walk_forward:
            print(f"    Walk-forward: {family} ...")
            try:
                wfa = WalkForwardAnalysis(
                    strategy_class=strategy_class,
                    param_grid=param_grid,
                    metric="sharpe_ratio",
                    initial_capital=10_000.0,
                    transaction_cost_bps=7.5,
                )
                wf_results = wfa.run(underlying=underlying, prices=prices)
                if wf_results.windows:
                    analysis.walkforward = build_walk_forward_result(wf_results)
                    wf_val = f"{analysis.walkforward.overfitting_ratio}"
                    wf_v = analysis.walkforward.verdict
                else:
                    print(f"    WARNING: no walk-forward windows for {family}.")
            except Exception as exc:
                print(f"    WARNING: walk-forward failed for {family}: {exc}")

        save_analysis(analysis, f"{family}__pbo_sweep")

        pbo_val = f"{analysis.pbo.pbo:.4f}" if analysis.pbo else "N/A"
        pbo_v = analysis.pbo.verdict if analysis.pbo else "N/A"
        dsr_val = f"{analysis.dsr.dsr:.4f}" if analysis.dsr else "N/A"
        dsr_v = analysis.dsr.verdict if analysis.dsr else "N/A"
        kf_frac = f"{analysis.kfold.fraction_positive:.0%}" if analysis.kfold else "N/A"
        kf_v = analysis.kfold.verdict if analysis.kfold else "N/A"

        row = {
            "family": family,
            "n_configs": return_matrix.shape[1],
            "dsr": dsr_val,
            "dsr_verdict": dsr_v,
            "kfold_frac_pos": kf_frac,
            "kfold_verdict": kf_v,
            "pbo": pbo_val,
            "pbo_verdict": pbo_v,
        }
        if walk_forward:
            row["wf_ratio"] = wf_val
            row["wf_verdict"] = wf_v
        pbo_rows.append(row)

    return pbo_rows


def run_spa_analysis(strategy_keys, results_dir) -> None:
    """White's RC / Hansen's SPA across all strategies vs the equal_weight benchmark.

    Writes results/spa_analysis.json and a per-strategy ``spa`` stub (the p-values
    plus this strategy's mean-differential rank) into each overfitting_analysis.json.
    """
    import json as _json

    from analytics.family_matrix import build_family_return_matrix
    from analytics.spa import compute_spa

    matrix = build_family_return_matrix(results_dir, strategy_keys)
    if matrix.empty or matrix.shape[1] < 2:
        print("  SPA skipped: need >= 2 strategies with aligned history.")
        return

    bench_col = "equal_weight" if "equal_weight" in matrix.columns else None
    if bench_col is None:
        benchmark = matrix.mean(axis=1)
        strat_matrix = matrix
        print("  SPA: no equal_weight column; using cross-sectional mean benchmark.")
    else:
        benchmark = matrix[bench_col]
        strat_matrix = matrix.drop(columns=[bench_col])

    result = compute_spa(strat_matrix, benchmark, expected_block=3, n_iter=1000, seed=0)

    spa_dict = result.to_dict()
    out_path = Path(results_dir) / "spa_analysis.json"
    with open(out_path, "w") as f:
        _json.dump(spa_dict, f, indent=2)

    # Per-strategy stub: rank by mean differential vs benchmark.
    diffs = (
        strat_matrix.sub(benchmark, axis=0).mean(axis=0).sort_values(ascending=False)
    )
    ranks = {k: i + 1 for i, k in enumerate(diffs.index)}
    for key in strat_matrix.columns:
        opath = schema_strategy_dir(RESULTS_DIR.parent, key) / OVERFITTING_FILE
        payload = _json.load(open(opath)) if opath.exists() else {"strategy_key": key}
        payload["spa"] = {
            "reality_check_pvalue": spa_dict["reality_check_pvalue"],
            "spa_pvalue_consistent": spa_dict["spa_pvalue_consistent"],
            "best_strategy": spa_dict["best_strategy"],
            "rank": ranks.get(key),
            "n_strategies": spa_dict["n_strategies"],
        }
        opath.parent.mkdir(parents=True, exist_ok=True)
        with open(opath, "w") as f:
            _json.dump(payload, f, indent=2)

    print(f"\nSPA / Reality Check (N={result.n_strategies}, T={result.n_obs})")
    print(f"  Best strategy        : {result.best_strategy}")
    print(f"  Reality Check p-value: {result.reality_check_pvalue:.4f}")
    print(f"  SPA consistent p     : {result.spa_pvalue_consistent:.4f}")
    print(f"  Saved to             : {out_path}\n")
