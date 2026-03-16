"""
Overfitting detection metrics for backtested trading strategies.

Implements:
- Deflated Sharpe Ratio (DSR): probability that observed Sharpe ratio is not
  due to selection bias across N parameter trials.
  Reference: Bailey & López de Prado (2014), "The Deflated Sharpe Ratio"
  https://ssrn.com/abstract=2460551

- Probability of Backtest Overfitting (PBO): fraction of Combinatorially
  Symmetric Cross-Validation (CSCV) partitions where the in-sample best
  parameter combination ranks below median out-of-sample.
  Reference: Bailey et al. (2014), "The Probability of Backtest Overfitting"
  http://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253

Adapted from the pypbo reference implementation (https://github.com/esvhd/pypbo).
"""
from __future__ import annotations

import itertools
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd
import scipy.special as sc
import scipy.stats as ss

logger = logging.getLogger(__name__)


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
class OverfittingAnalysis:
    """Combined overfitting analysis output for a strategy."""

    strategy_key: str
    dsr: Optional[DSRResult]
    pbo: Optional[PBOResult]
    n_param_combinations: int
    analysis_date: str
    config: Dict[str, Any]
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core math helpers
# ---------------------------------------------------------------------------


def _expected_max_sharpe(n: int) -> float:
    """
    Expected maximum of N IID standard Normal draws E[max{Z_n}].

    Used to compute the DSR reference Sharpe SR₀.
    Requires N >= 2; raises ValueError otherwise.

    Formula from Bailey & López de Prado (2014):
        E[max] = (1 - γ) * Φ⁻¹(1 - 1/N) + γ * Φ⁻¹(1 - e⁻¹/N)
    where γ is the Euler-Mascheroni constant ≈ 0.5772.
    """
    if n < 2:
        raise ValueError(f"n_trials must be >= 2 for DSR, got {n}.")
    gamma = np.euler_gamma  # ≈ 0.5772156649
    term1 = (1 - gamma) * ss.norm.ppf(1 - 1.0 / n)
    term2 = gamma * ss.norm.ppf(1 - math.exp(-1) / n)
    return term1 + term2


def _psr(
    sharpe: float,
    t: int,
    skew: float,
    kurtosis_raw: float,
    target_sharpe: float = 0.0,
) -> float:
    """
    Probabilistic Sharpe Ratio (PSR).

    Parameters
    ----------
    sharpe : float
        Observed Sharpe ratio (in per-period units, not annualised).
    t : int
        Number of return observations.
    skew : float
        Skewness of the return series.
    kurtosis_raw : float
        Raw (non-excess) kurtosis of the return series.
    target_sharpe : float
        Benchmark Sharpe ratio (SR₀ for DSR, 0 for PSR).

    Returns
    -------
    float
        Probability in [0, 1].
    """
    denom = math.sqrt(
        1.0 - skew * sharpe + sharpe**2 * (kurtosis_raw - 1.0) / 4.0
    )
    if denom <= 0:
        logger.warning("PSR denominator <= 0; returning 0.")
        return 0.0
    z = (sharpe - target_sharpe) * math.sqrt(t - 1) / denom
    return float(ss.norm.cdf(z))


def _sharpe_per_period(returns: np.ndarray) -> float:
    """Un-annualised Sharpe ratio (mean / std, ddof=1)."""
    std = np.std(returns, ddof=1)
    if std == 0:
        return 0.0
    return float(np.mean(returns) / std)


def _sharpe_matrix(matrix: np.ndarray) -> np.ndarray:
    """
    Vectorised per-period Sharpe across columns of a 2D numpy array.

    Returns array of shape (N,).
    """
    means = np.mean(matrix, axis=0)
    stds = np.std(matrix, axis=0, ddof=1)
    stds = np.where(stds == 0, np.nan, stds)
    return means / stds


# ---------------------------------------------------------------------------
# Public API: DSR
# ---------------------------------------------------------------------------


def calculate_deflated_sharpe_ratio(
    returns: pd.Series,
    n_trials: int,
    periods_per_year: int = 12,
    sharpe_std: Optional[float] = None,
    threshold_pass: float = 0.95,
    threshold_warn: float = 0.80,
) -> DSRResult:
    """
    Calculate the Deflated Sharpe Ratio (DSR).

    The DSR is the PSR evaluated against an inflated benchmark SR₀ that
    accounts for multiple-testing bias from evaluating N parameter
    combinations. It answers: "Given that we picked the best strategy from
    N trials, what is the probability the observed Sharpe is real?"

    Parameters
    ----------
    returns : pd.Series
        Portfolio return series (percentage returns, one entry per rebalance).
    n_trials : int
        Number of parameter combinations tested (N). Must be >= 2.
    periods_per_year : int
        Annualisation factor. 12 for monthly, 252 for daily.
    sharpe_std : float, optional
        Standard deviation of Sharpe ratios across all N configurations.
        If provided, SR₀ = sharpe_std * E[max_N].
        If None, computes SR₀ = E[max_N] / sqrt(T-1) (single-series fallback).
    threshold_pass : float
        DSR >= this → PASS.
    threshold_warn : float
        DSR >= this → WARN, else FAIL.

    Returns
    -------
    DSRResult
    """
    arr = returns.dropna().values
    t = len(arr)
    if t < 10:
        raise ValueError(
            f"Return series too short for DSR (T={t}). Need at least 10 periods."
        )

    # Per-period Sharpe (un-annualised for moments calculation)
    sr_period = _sharpe_per_period(arr)
    sr_annual = sr_period * math.sqrt(periods_per_year)

    skew = float(ss.skew(arr, bias=False))
    # pandas .kurtosis() returns excess (Fisher); scipy same with fisher=True
    excess_kurt = float(ss.kurtosis(arr, bias=False, fisher=True))
    kurtosis_raw = excess_kurt + 3.0

    # SR₀: expected max Sharpe under null
    e_max = _expected_max_sharpe(n_trials)

    if sharpe_std is not None:
        target_period = sharpe_std * e_max
    else:
        # Without cross-config std, use 1/sqrt(T-1) as unit std estimate
        target_period = e_max / math.sqrt(t - 1)

    dsr_value = _psr(
        sharpe=sr_period,
        t=t,
        skew=skew,
        kurtosis_raw=kurtosis_raw,
        target_sharpe=target_period,
    )

    # SR₀ annualised for display
    sr_reference_annual = target_period * math.sqrt(periods_per_year)

    if dsr_value >= threshold_pass:
        verdict = "PASS"
    elif dsr_value >= threshold_warn:
        verdict = "WARN"
    else:
        verdict = "FAIL"

    return DSRResult(
        dsr=round(dsr_value, 6),
        observed_sharpe=round(sr_annual, 4),
        sharpe_reference=round(sr_reference_annual, 4),
        n_trials=n_trials,
        t_periods=t,
        skewness=round(skew, 4),
        excess_kurtosis=round(excess_kurt, 4),
        verdict=verdict,
        threshold_pass=threshold_pass,
        threshold_warn=threshold_warn,
    )


# ---------------------------------------------------------------------------
# Public API: PBO
# ---------------------------------------------------------------------------


def calculate_pbo(
    return_matrix: pd.DataFrame,
    s_subsets: int = 16,
    metric_fn: Optional[Callable[[np.ndarray], np.ndarray]] = None,
    oos_loss_threshold: float = 0.0,
    threshold_pass: float = 0.30,
    threshold_warn: float = 0.50,
) -> PBOResult:
    """
    Calculate the Probability of Backtest Overfitting (PBO) via CSCV.

    Parameters
    ----------
    return_matrix : pd.DataFrame
        Shape (T, N) — rows=time periods, columns=parameter combinations.
        All series must share the same DatetimeIndex.
    s_subsets : int
        Number of equal time partitions (must be even). Paper suggests 16.
    metric_fn : callable, optional
        f(2D numpy array of shape (T_sub, N)) -> array of shape (N,).
        Defaults to per-period Sharpe ratio.
    oos_loss_threshold : float
        Cutoff for prob_oos_loss calculation. For Sharpe, use 0.
    threshold_pass : float
        PBO <= this → PASS.
    threshold_warn : float
        PBO <= this → WARN, else FAIL.

    Returns
    -------
    PBOResult
    """
    if s_subsets % 2 != 0:
        raise ValueError(f"s_subsets must be even, got {s_subsets}.")

    m = return_matrix.values  # shape (T, N)
    t_total, n_configs = m.shape

    if t_total < s_subsets:
        raise ValueError(
            f"Too few periods (T={t_total}) for s_subsets={s_subsets}. "
            f"Reduce --s-subsets."
        )

    if t_total / s_subsets < 5:
        logger.warning(
            "T/S = %.1f < 5. CSCV partitions are very small; consider "
            "reducing s_subsets to %d.",
            t_total / s_subsets,
            s_subsets // 2,
        )

    # Trim so T is divisible by S
    residual = t_total % s_subsets
    if residual:
        m = m[residual:]
        t_total = m.shape[0]

    sub_t = t_total // s_subsets

    if metric_fn is None:
        metric_fn = _sharpe_matrix

    # Build list of (index, chunk_array) tuples
    chunks = [(i, m[i * sub_t : (i + 1) * sub_t, :]) for i in range(s_subsets)]
    chunk_arrays = np.array([c for _, c in chunks])  # (S, sub_T, N)
    all_indices = set(range(s_subsets))

    logits: List[float] = []
    overfit_flags: List[float] = []
    is_metrics_best: List[float] = []
    oos_metrics_best: List[float] = []

    for is_indices in itertools.combinations(range(s_subsets), s_subsets // 2):
        oos_indices = sorted(all_indices - set(is_indices))
        is_sorted = sorted(is_indices)

        # Stack IS and OOS chunks preserving time order
        j_is = np.concatenate(chunk_arrays[list(is_sorted), :], axis=0)
        j_oos = np.concatenate(chunk_arrays[oos_indices, :], axis=0)

        r_is = metric_fn(j_is)  # (N,)
        r_oos = metric_fn(j_oos)  # (N,)

        # Replace NaN with -inf so they rank last
        r_is = np.where(np.isfinite(r_is), r_is, -np.inf)
        r_oos = np.where(np.isfinite(r_oos), r_oos, -np.inf)

        # Best IS config (highest rank)
        is_ranks = ss.rankdata(r_is)
        best_config = int(np.argmax(is_ranks))

        # OOS rank of that config (1-based)
        oos_ranks = ss.rankdata(r_oos)
        oos_rank_of_best = oos_ranks[best_config]

        # Normalise: divide by (N+1) to avoid logit(1) = inf
        w_bar = float(oos_rank_of_best) / (n_configs + 1)
        logit_val = float(sc.logit(w_bar))

        logits.append(logit_val)
        # logit <= 0 means OOS rank <= median → overfitting
        overfit_flags.append(1.0 if logit_val <= 0 else 0.0)

        is_metrics_best.append(float(r_is[best_config]))
        oos_metrics_best.append(float(r_oos[best_config]))

    n_combinations = len(logits)
    pbo_value = float(np.mean(overfit_flags))
    prob_oos_loss = float(
        np.mean([1.0 if v < oos_loss_threshold else 0.0 for v in oos_metrics_best])
    )

    if pbo_value <= threshold_pass:
        verdict = "PASS"
    elif pbo_value <= threshold_warn:
        verdict = "WARN"
    else:
        verdict = "FAIL"

    return PBOResult(
        pbo=round(pbo_value, 6),
        prob_oos_loss=round(prob_oos_loss, 6),
        n_combinations=n_combinations,
        s_subsets=s_subsets,
        n_configs=n_configs,
        logit_scores=[round(v, 6) for v in logits],
        verdict=verdict,
        threshold_pass=threshold_pass,
        threshold_warn=threshold_warn,
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run_overfitting_analysis(
    strategy_key: str,
    strategy_returns: pd.Series,
    return_matrix: Optional[pd.DataFrame],
    param_grid: Dict[str, Any],
    periods_per_year: int = 12,
    sharpe_std: Optional[float] = None,
    s_subsets: int = 16,
    dsr_threshold_pass: float = 0.95,
    dsr_threshold_warn: float = 0.80,
    pbo_threshold_pass: float = 0.30,
    pbo_threshold_warn: float = 0.50,
    oos_loss_threshold: float = 0.0,
) -> OverfittingAnalysis:
    """
    Run DSR and (optionally) PBO for a strategy and return combined analysis.

    Parameters
    ----------
    strategy_key : str
        Strategy identifier, e.g. 'hrp_ward'.
    strategy_returns : pd.Series
        Return series of the selected/best parameter combination.
    return_matrix : pd.DataFrame or None
        Shape (T, N) with all parameter combinations' returns. If None,
        PBO is skipped.
    param_grid : dict
        Parameter grid used (stored in config for reproducibility).
    periods_per_year : int
        12 for monthly rebalancing, 252 for daily.
    sharpe_std : float, optional
        Std of Sharpe ratios across N configs. If return_matrix is provided
        this is computed automatically; pass explicitly only for Mode 2.
    s_subsets : int
        CSCV partition count for PBO.
    dsr_threshold_pass / dsr_threshold_warn : float
        DSR verdict thresholds.
    pbo_threshold_pass / pbo_threshold_warn : float
        PBO verdict thresholds.
    oos_loss_threshold : float
        Metric threshold for prob_oos_loss (0 for Sharpe).

    Returns
    -------
    OverfittingAnalysis
    """
    errors: List[str] = []
    n_configs = 1

    # Compute sharpe_std from return_matrix if available
    if return_matrix is not None:
        n_configs = return_matrix.shape[1]
        sharpe_arr = _sharpe_matrix(return_matrix.values)
        sharpe_std = float(np.std(sharpe_arr[np.isfinite(sharpe_arr)], ddof=1))

    dsr_result: Optional[DSRResult] = None
    try:
        dsr_result = calculate_deflated_sharpe_ratio(
            returns=strategy_returns,
            n_trials=max(n_configs, 2),
            periods_per_year=periods_per_year,
            sharpe_std=sharpe_std,
            threshold_pass=dsr_threshold_pass,
            threshold_warn=dsr_threshold_warn,
        )
    except Exception as exc:
        msg = f"DSR calculation failed: {exc}"
        logger.warning(msg)
        errors.append(msg)

    pbo_result: Optional[PBOResult] = None
    if return_matrix is not None and n_configs >= 2:
        try:
            pbo_result = calculate_pbo(
                return_matrix=return_matrix,
                s_subsets=s_subsets,
                oos_loss_threshold=oos_loss_threshold,
                threshold_pass=pbo_threshold_pass,
                threshold_warn=pbo_threshold_warn,
            )
        except Exception as exc:
            msg = f"PBO calculation failed: {exc}"
            logger.warning(msg)
            errors.append(msg)
    elif return_matrix is None:
        logger.info("return_matrix not provided; skipping PBO.")

    return OverfittingAnalysis(
        strategy_key=strategy_key,
        dsr=dsr_result,
        pbo=pbo_result,
        n_param_combinations=n_configs,
        analysis_date=datetime.now(timezone.utc).isoformat(),
        config={
            "param_grid": param_grid,
            "periods_per_year": periods_per_year,
            "s_subsets": s_subsets,
        },
        errors=errors,
    )


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

    return result
