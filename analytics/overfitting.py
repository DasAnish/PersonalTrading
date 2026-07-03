"""
Overfitting detection metrics for backtested trading strategies.

Implements: Deflated Sharpe Ratio (DSR) — Bailey & López de Prado (2014),
"The Deflated Sharpe Ratio", https://ssrn.com/abstract=2460551 (probability
the observed Sharpe isn't selection bias across N trials); Probability of
Backtest Overfitting (PBO) via CSCV — Bailey et al. (2014), "The
Probability of Backtest Overfitting", http://papers.ssrn.com/sol3/papers.
cfm?abstract_id=2326253; K-Fold Temporal Stability (fraction of k equal
time folds with positive Sharpe, optionally purged/embargoed — Phase 6);
Minimum Backtest Length (MinBTL/MinTRL) — Bailey, Borwein, López de Prado
& Zhu (2014), "Pseudo-Mathematics and Financial Charlatanism", Notices of
the AMS 61(5) (minimum years of track record needed for an observed Sharpe
to beat the expected-max-under-null of N trials).

Adapted from the pypbo reference implementation (https://github.com/esvhd/pypbo).
Result dataclasses and ``overfitting_analysis_to_dict`` live in
``analytics.overfitting_results`` and are re-exported here for compatibility.
"""

from __future__ import annotations

import itertools
import logging
import math
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd
import scipy.special as sc
import scipy.stats as ss

from optimization.splitters import contiguous_folds, embargoed_fold_indices

from .overfitting_results import (  # noqa: F401 (re-exported for compatibility)
    DSRResult,
    KFoldResult,
    MinBTLResult,
    OverfittingAnalysis,
    PBOResult,
    WalkForwardResult,
    build_walk_forward_result,
    overfitting_analysis_to_dict,
    walk_forward_to_dict,
)

logger = logging.getLogger(__name__)


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

    ``sharpe``: observed Sharpe (per-period, not annualised). ``t``: number
    of return observations. ``skew``/``kurtosis_raw``: return series
    skewness / raw (non-excess) kurtosis. ``target_sharpe``: benchmark
    Sharpe (SR₀ for DSR, 0 for PSR). Returns a probability in [0, 1].
    """
    denom = math.sqrt(1.0 - skew * sharpe + sharpe**2 * (kurtosis_raw - 1.0) / 4.0)
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

    ``n_trials`` (N) must be >= 2. ``periods_per_year``: 12 monthly / 252
    daily. ``sharpe_std`` (optional): std of Sharpes across all N configs —
    if given, SR₀ = sharpe_std * E[max_N]; else SR₀ = E[max_N] / sqrt(T-1)
    (single-series fallback). ``threshold_pass``/``threshold_warn``: DSR
    verdict cutoffs.

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

    ``return_matrix`` shape (T, N): rows=time periods, columns=parameter
    combinations, all sharing the same DatetimeIndex. ``s_subsets``: number
    of equal time partitions (must be even; paper suggests 16).
    ``metric_fn`` (optional): f(2D array (T_sub, N)) -> array (N,), default
    per-period Sharpe. ``oos_loss_threshold``: cutoff for prob_oos_loss (0
    for Sharpe). ``threshold_pass``/``threshold_warn``: PBO verdict cutoffs
    (PBO <= threshold_pass -> PASS, <= threshold_warn -> WARN, else FAIL).

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


def calculate_kfold_stability(
    returns: pd.Series,
    n_folds: int = 10,
    periods_per_year: int = 12,
    threshold_pass: float = 0.70,
    threshold_warn: float = 0.50,
    embargo_periods: int = 0,
) -> KFoldResult:
    """
    K-fold temporal stability, optionally purged/embargoed (Phase 6).

    Splits returns into ``n_folds`` equal consecutive windows, computes the
    annualised Sharpe of each, and reports what fraction are positive
    (spots strategies that only work in one lucky era). ``embargo_periods``
    applies ``splitters.apply_embargo`` at each internal fold boundary,
    dropping that many observations from each side of a shared boundary
    before computing that fold's Sharpe — guards against lookback-window
    leakage across the split (López de Prado, *AFML*, ch. 7).
    ``embargo_periods=0`` (default) reproduces the original fold Sharpes
    exactly. ``periods_per_year``: 12 monthly / 252 daily.
    ``threshold_pass``/``threshold_warn``: fraction_positive cutoffs.

    Raises ValueError if T < n_folds*3, embargo_periods < 0, or an embargo
    leaves < 2 observations in a fold.
    """
    arr = returns.dropna().values
    t = len(arr)
    min_periods = n_folds * 3
    if t < min_periods:
        raise ValueError(
            f"Return series too short for {n_folds}-fold analysis "
            f"(T={t}, need >= {min_periods})."
        )
    if embargo_periods < 0:
        raise ValueError(
            f"embargo_periods must be non-negative, got {embargo_periods}."
        )

    # Consecutive equal-size folds; leading residual rows are discarded so
    # T is divisible by n_folds (preserves recency of the most recent data).
    folds = contiguous_folds(t, n_folds)
    fold_sharpes: List[float] = []

    for i, (start, end) in enumerate(folds):
        fold_idx = embargoed_fold_indices(folds, i, embargo_periods)
        if len(fold_idx) < 2:
            raise ValueError(
                f"embargo_periods={embargo_periods} leaves < 2 observations "
                f"in fold {i} (original size {end - start}); reduce "
                "embargo_periods or n_folds."
            )
        fold = arr[fold_idx]
        sr_period = _sharpe_per_period(fold)
        sr_annual = sr_period * math.sqrt(periods_per_year)
        fold_sharpes.append(round(sr_annual, 4))

    mean_sharpe = float(np.mean(fold_sharpes))
    std_sharpe = float(np.std(fold_sharpes, ddof=1)) if n_folds > 1 else 0.0
    fraction_positive = float(np.mean([1.0 if s > 0 else 0.0 for s in fold_sharpes]))
    worst_fold_sharpe = float(np.min(fold_sharpes))

    if fraction_positive >= threshold_pass:
        verdict = "PASS"
    elif fraction_positive >= threshold_warn:
        verdict = "WARN"
    else:
        verdict = "FAIL"

    return KFoldResult(
        n_folds=n_folds,
        fold_sharpes=fold_sharpes,
        mean_sharpe=round(mean_sharpe, 4),
        std_sharpe=round(std_sharpe, 4),
        fraction_positive=round(fraction_positive, 4),
        worst_fold_sharpe=worst_fold_sharpe,
        verdict=verdict,
        threshold_pass=threshold_pass,
        threshold_warn=threshold_warn,
        embargo_periods=embargo_periods,
    )


def calculate_minbtl(
    observed_sharpe_annualized: float,
    n_trials: int,
    actual_years: float,
    warn_ratio: float = 0.8,
) -> MinBTLResult:
    """
    Minimum Backtest Length (MinBTL, a.k.a. Minimum Track Record Length).

    Minimum years of track record needed for an observed annualised Sharpe
    to be distinguishable from the expected *maximum* Sharpe obtainable by
    chance across ``n_trials`` configs. Formula (Bailey, Borwein, López de
    Prado & Zhu (2014), "Pseudo-Mathematics and Financial Charlatanism",
    Notices of the AMS 61(5); same E[max_N] term as the DSR reference SR₀
    in Bailey & López de Prado (2014), "The Deflated Sharpe Ratio")::

        MinBTL ≈ ( E[max_N] / SR )²   [years]

    ``E[max_N]`` = ``_expected_max_sharpe(n_trials)``; ``SR`` = ANNUALISED
    Sharpe of the selected strategy. Simplified MinTRL: omits the
    skew/kurtosis correction ``_psr`` applies for DSR (order-of-magnitude
    check, not an exact bound), and relies on the same "reference Sharpe
    scales as 1/sqrt(T)" assumption as ``calculate_deflated_sharpe_ratio``'s
    single-series fallback. ``n_trials`` >= 2.

    Non-positive Sharpe -> ratio undefined -> min_years=inf, verdict FAIL.
    ``warn_ratio`` (default 0.8): WARN if actual_years is between
    ``warn_ratio * min_years`` and ``min_years``.

    Returns
    -------
    MinBTLResult
    """
    e_max = _expected_max_sharpe(n_trials)

    if observed_sharpe_annualized <= 0:
        min_years = float("inf")
    else:
        min_years = (e_max / observed_sharpe_annualized) ** 2

    if actual_years >= min_years:
        verdict = "PASS"
    elif math.isfinite(min_years) and actual_years >= warn_ratio * min_years:
        verdict = "WARN"
    else:
        verdict = "FAIL"

    return MinBTLResult(
        min_years=round(min_years, 4) if math.isfinite(min_years) else min_years,
        actual_years=round(actual_years, 4),
        n_trials=n_trials,
        observed_sharpe=round(observed_sharpe_annualized, 4),
        verdict=verdict,
        warn_ratio=warn_ratio,
    )


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
    n_folds: int = 10,
    kfold_threshold_pass: float = 0.70,
    kfold_threshold_warn: float = 0.50,
    embargo_periods: int = 0,
    minbtl_warn_ratio: float = 0.8,
) -> OverfittingAnalysis:
    """
    Run DSR, (optionally) PBO, k-fold stability, and MinBTL for a strategy
    and return combined analysis.

    ``strategy_returns`` is the selected/best combination's return series;
    ``return_matrix`` (T, N) holds all combinations' returns (PBO skipped
    if None). ``param_grid`` is stored in ``config`` for reproducibility.
    ``periods_per_year``: 12 monthly / 252 daily. ``sharpe_std`` (optional):
    std of Sharpes across N configs, auto-computed from ``return_matrix``
    when available. ``s_subsets``: CSCV partition count for PBO.
    ``{dsr,pbo,kfold}_threshold_{pass,warn}``: verdict cutoffs for each
    section. ``oos_loss_threshold``: cutoff for PBO's prob_oos_loss.
    ``n_folds``: k-fold window count. ``embargo_periods``: purge/embargo
    window (periods) for k-fold stability, see ``calculate_kfold_stability``
    (0 = classic k-fold). ``minbtl_warn_ratio``: WARN ratio for MinBTL, see
    ``calculate_minbtl``.

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

    kfold_result: Optional[KFoldResult] = None
    try:
        kfold_result = calculate_kfold_stability(
            returns=strategy_returns,
            n_folds=n_folds,
            periods_per_year=periods_per_year,
            threshold_pass=kfold_threshold_pass,
            threshold_warn=kfold_threshold_warn,
            embargo_periods=embargo_periods,
        )
    except Exception as exc:
        msg = f"K-fold stability calculation failed: {exc}"
        logger.warning(msg)
        errors.append(msg)

    minbtl_result: Optional[MinBTLResult] = None
    try:
        arr = strategy_returns.dropna()
        t_obs = len(arr)
        if dsr_result is not None:
            sr_annual = dsr_result.observed_sharpe
        else:
            sr_annual = _sharpe_per_period(arr.values) * math.sqrt(periods_per_year)
        minbtl_result = calculate_minbtl(
            observed_sharpe_annualized=sr_annual,
            n_trials=max(n_configs, 2),
            actual_years=t_obs / periods_per_year,
            warn_ratio=minbtl_warn_ratio,
        )
    except Exception as exc:
        msg = f"MinBTL calculation failed: {exc}"
        logger.warning(msg)
        errors.append(msg)

    return OverfittingAnalysis(
        strategy_key=strategy_key,
        dsr=dsr_result,
        pbo=pbo_result,
        kfold=kfold_result,
        minbtl=minbtl_result,
        n_param_combinations=n_configs,
        analysis_date=datetime.now(timezone.utc).isoformat(),
        config={
            "param_grid": param_grid,
            "periods_per_year": periods_per_year,
            "s_subsets": s_subsets,
            "n_folds": n_folds,
            "embargo_periods": embargo_periods,
        },
        errors=errors,
    )
