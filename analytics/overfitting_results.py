"""
Result dataclasses and JSON serialisation for the overfitting analysis suite.

Split out of ``analytics/overfitting.py`` (Phase 6) purely to keep that file
under the project's 600-line limit — this module has no behaviour of its
own, only data containers and ``*_to_dict`` serialisers. All names here are
re-exported from ``analytics/overfitting.py`` so existing imports
(``from analytics.overfitting import DSRResult, ...``) keep working
unchanged.

The on-disk ``overfitting_analysis.json`` produced by
``overfitting_analysis_to_dict`` is a single unified file per strategy.
Every top-level section (``dsr``, ``pbo``, ``kfold``, ``minbtl``,
``walkforward``, and future ``cpcv`` / ``bootstrap`` / ``spa`` sections) is
optional and serialises to ``null`` when not computed — every reader
(dashboard, CLI report printer, tests) must tolerate that.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class DSRResult:
    """Result of the Deflated Sharpe Ratio calculation."""

    dsr: float
    """DSR probability in [0, 1]. Higher = less likely to be due to luck."""

    observed_sharpe: float
    """Annualised Sharpe ratio of the evaluated strategy."""

    sharpe_reference: float
    """SR₀: expected max Sharpe under null (annualised), used as PSR target."""

    n_trials: int
    """Number of parameter combinations tested (N)."""

    t_periods: int
    """Number of return observations used."""

    skewness: float
    """Skewness of the return series."""

    excess_kurtosis: float
    """Excess kurtosis (Fisher) of the return series."""

    verdict: str
    """PASS / WARN / FAIL based on thresholds."""

    threshold_pass: float = 0.95
    threshold_warn: float = 0.80


@dataclass
class PBOResult:
    """Result of the Probability of Backtest Overfitting (CSCV) calculation."""

    pbo: float
    """Fraction of IS-best configs that underperform OOS. Lower = better."""

    prob_oos_loss: float
    """Fraction of partitions where IS-best config has negative OOS metric."""

    n_combinations: int
    """Number of C(S, S/2) partitions evaluated."""

    s_subsets: int
    """Number of equal time-subsets S."""

    n_configs: int
    """Number of parameter combinations (columns in return matrix)."""

    logit_scores: List[float]
    """logit(OOS rank / (N+1)) for each partition — useful for distribution plot."""

    verdict: str
    """PASS / WARN / FAIL based on thresholds."""

    threshold_pass: float = 0.30
    threshold_warn: float = 0.50


@dataclass
class KFoldResult:
    """Result of k-fold temporal stability analysis."""

    n_folds: int
    """Number of equal time folds the return series was split into."""

    fold_sharpes: List[float]
    """Annualised Sharpe ratio computed for each fold."""

    mean_sharpe: float
    """Mean of per-fold Sharpe ratios."""

    std_sharpe: float
    """Standard deviation of per-fold Sharpe ratios."""

    fraction_positive: float
    """Fraction of folds with Sharpe > 0. 1.0 = all folds positive."""

    worst_fold_sharpe: float
    """Lowest per-fold Sharpe (worst time period)."""

    verdict: str
    """PASS / WARN / FAIL based on fraction_positive thresholds."""

    threshold_pass: float = 0.70
    threshold_warn: float = 0.50

    embargo_periods: int = 0
    """Observations dropped adjacent to each internal fold boundary
    (purged/embargoed k-fold, Phase 6). 0 = classic contiguous k-fold."""


@dataclass
class MinBTLResult:
    """
    Result of the Minimum Backtest Length (MinBTL / MinTRL) calculation.

    See ``analytics.overfitting.calculate_minbtl`` for the formula and
    citation.
    """

    min_years: float
    """Minimum years of track record needed for the observed Sharpe to be
    distinguishable from the expected-max-under-null of ``n_trials``
    configurations. ``inf`` when observed_sharpe <= 0 (undefined)."""

    actual_years: float
    """Actual length of the backtest track record, in years."""

    n_trials: int
    """Number of parameter combinations tested (N), same N used for DSR."""

    observed_sharpe: float
    """Annualised Sharpe ratio used in the calculation."""

    verdict: str
    """PASS if actual_years >= min_years, WARN if within warn_ratio of the
    minimum, else FAIL."""

    warn_ratio: float = 0.8


@dataclass
class WalkForwardResult:
    """Serialisable summary of an ``optimization.walk_forward.WalkForwardResults``
    run, for the ``walkforward`` section of ``overfitting_analysis.json``."""

    avg_in_sample: float
    avg_out_sample: float
    overfitting_ratio: Optional[float]
    """avg_in_sample / avg_out_sample. None when avg_out_sample == 0 (the
    ``inf`` produced by ``WalkForwardResults.__post_init__`` is not JSON
    serialisable, so it is represented as null)."""

    n_windows: int
    target_metric: str
    verdict: str
    """PASS if ratio < threshold_pass, WARN if < threshold_warn, else FAIL.
    A null (inf) ratio is always FAIL."""

    threshold_pass: float = 1.5
    threshold_warn: float = 2.5


@dataclass
class OverfittingAnalysis:
    """Combined overfitting analysis output for a strategy."""

    strategy_key: str
    dsr: Optional[DSRResult]
    pbo: Optional[PBOResult]
    n_param_combinations: int
    analysis_date: str
    config: Dict[str, Any]
    kfold: Optional[KFoldResult] = None
    errors: List[str] = field(default_factory=list)
    minbtl: Optional[MinBTLResult] = None
    walkforward: Optional[WalkForwardResult] = None


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def overfitting_analysis_to_dict(analysis: OverfittingAnalysis) -> Dict[str, Any]:
    """Serialise OverfittingAnalysis to a JSON-compatible dict."""
    result: Dict[str, Any] = {
        "strategy_key": analysis.strategy_key,
        "analysis_date": analysis.analysis_date,
        "n_param_combinations": analysis.n_param_combinations,
        "config": analysis.config,
        "errors": analysis.errors,
        "dsr": None,
        "pbo": None,
        "kfold": None,
        "minbtl": None,
        "walkforward": None,
    }

    if analysis.dsr is not None:
        d = analysis.dsr
        result["dsr"] = {
            "dsr": d.dsr,
            "observed_sharpe": d.observed_sharpe,
            "sharpe_reference": d.sharpe_reference,
            "n_trials": d.n_trials,
            "t_periods": d.t_periods,
            "skewness": d.skewness,
            "excess_kurtosis": d.excess_kurtosis,
            "verdict": d.verdict,
            "threshold_pass": d.threshold_pass,
            "threshold_warn": d.threshold_warn,
        }

    if analysis.pbo is not None:
        p = analysis.pbo
        result["pbo"] = {
            "pbo": p.pbo,
            "prob_oos_loss": p.prob_oos_loss,
            "n_combinations": p.n_combinations,
            "s_subsets": p.s_subsets,
            "n_configs": p.n_configs,
            "logit_scores": p.logit_scores,
            "verdict": p.verdict,
            "threshold_pass": p.threshold_pass,
            "threshold_warn": p.threshold_warn,
        }

    if analysis.kfold is not None:
        k = analysis.kfold
        result["kfold"] = {
            "n_folds": k.n_folds,
            "fold_sharpes": k.fold_sharpes,
            "mean_sharpe": k.mean_sharpe,
            "std_sharpe": k.std_sharpe,
            "fraction_positive": k.fraction_positive,
            "worst_fold_sharpe": k.worst_fold_sharpe,
            "verdict": k.verdict,
            "threshold_pass": k.threshold_pass,
            "threshold_warn": k.threshold_warn,
            "embargo_periods": k.embargo_periods,
        }

    if analysis.minbtl is not None:
        m = asdict(analysis.minbtl)
        # inf isn't valid JSON (json.dump would emit the non-standard
        # "Infinity" token, which JS's JSON.parse rejects) — represent an
        # undefined MinBTL (non-positive Sharpe) as null instead.
        if not math.isfinite(m["min_years"]):
            m["min_years"] = None
        result["minbtl"] = m

    if analysis.walkforward is not None:
        result["walkforward"] = asdict(analysis.walkforward)

    return result


# ---------------------------------------------------------------------------
# Walk-forward serialisation helpers
# ---------------------------------------------------------------------------


def build_walk_forward_result(results: Any) -> WalkForwardResult:
    """
    Convert an ``optimization.walk_forward.WalkForwardResults`` instance into
    the serialisable ``WalkForwardResult`` dataclass, applying the verdict
    thresholds:

        overfitting_ratio < 1.5  -> PASS
        overfitting_ratio < 2.5  -> WARN
        else (including inf)     -> FAIL

    ``results`` is duck-typed (any object exposing ``avg_in_sample``,
    ``avg_out_sample``, ``overfitting_ratio``, ``windows``, and
    ``target_metric``) to avoid a hard import dependency on
    ``optimization.walk_forward`` from this module.
    """
    ratio = results.overfitting_ratio
    is_finite = math.isfinite(ratio)

    if not is_finite:
        verdict = "FAIL"
    elif ratio < 1.5:
        verdict = "PASS"
    elif ratio < 2.5:
        verdict = "WARN"
    else:
        verdict = "FAIL"

    return WalkForwardResult(
        avg_in_sample=round(float(results.avg_in_sample), 4),
        avg_out_sample=round(float(results.avg_out_sample), 4),
        overfitting_ratio=round(float(ratio), 4) if is_finite else None,
        n_windows=len(results.windows),
        target_metric=results.target_metric,
        verdict=verdict,
    )


def walk_forward_to_dict(results: Any) -> Dict[str, Any]:
    """Serialise a ``WalkForwardResults`` object directly to a JSON-safe dict."""
    return asdict(build_walk_forward_result(results))
