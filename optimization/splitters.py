"""
Pure time-series index-splitting utilities.

These functions contain no strategy-optimization or I/O logic — they take
integer sizes and return integer index boundaries. This keeps the
train/test splitting math in one place, shared by:

- ``analytics/overfitting.py`` (``calculate_kfold_stability``): consecutive
  equal-size folds for temporal stability analysis.
- ``optimization/walk_forward.py`` (``WalkForwardAnalysis``): rolling
  in-sample/out-of-sample windows.
- Future phases (CPCV, purged k-fold): ``apply_embargo`` and ``purge`` are
  the building blocks for embargoed/purged cross-validation.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple


def contiguous_folds(t: int, n_folds: int) -> List[Tuple[int, int]]:
    """
    Split ``t`` observations into ``n_folds`` equal-size consecutive
    ``[start, end)`` windows.

    If ``t`` does not divide evenly by ``n_folds``, the leading
    ``t % n_folds`` observations are discarded (not assigned to any fold),
    so all folds are equal-sized and the most recent data is preserved.
    This mirrors the residual-handling previously inlined in
    ``calculate_kfold_stability``.

    Parameters
    ----------
    t : int
        Total number of observations.
    n_folds : int
        Number of equal-size folds to split into. Must be positive and
        <= t.

    Returns
    -------
    List of ``(start, end)`` index tuples into an array of length ``t``.
    Fold ``i`` covers indices ``[start, end)``. The first fold's ``start``
    equals the discarded residual count (0 if ``t`` divides evenly).

    Example
    -------
    >>> contiguous_folds(10, 3)
    [(1, 4), (4, 7), (7, 10)]
    """
    if n_folds <= 0:
        raise ValueError(f"n_folds must be positive, got {n_folds}.")
    if t < n_folds:
        raise ValueError(f"t ({t}) must be >= n_folds ({n_folds}).")

    residual = t % n_folds
    fold_size = (t - residual) // n_folds

    folds = []
    for i in range(n_folds):
        start = residual + i * fold_size
        end = start + fold_size
        folds.append((start, end))
    return folds


def rolling_windows(
    n_days: int, in_sample: int, out_sample: int, step: int
) -> List[Tuple[int, int, int, int]]:
    """
    Compute rolling in-sample / out-of-sample window index boundaries.

    Extracted from ``WalkForwardAnalysis.run`` so the pure index math can
    be tested and reused independently of the strategy-optimization loop.

    Parameters
    ----------
    n_days : int
        Total number of available observations (e.g. trading days).
    in_sample : int
        Number of observations in each in-sample window.
    out_sample : int
        Number of observations in each out-of-sample window.
    step : int
        Number of observations to advance the window start between
        iterations. Must be positive.

    Returns
    -------
    List of ``(is_start, is_end, oos_start, oos_end)`` index tuples, all
    0-based and inclusive, into an array of length ``n_days``. Iteration
    stops once a full in-sample + out-of-sample window no longer fits
    within ``n_days``.

    Example
    -------
    >>> rolling_windows(n_days=10, in_sample=4, out_sample=2, step=2)
    [(0, 3, 4, 5), (2, 5, 6, 7), (4, 7, 8, 9)]
    """
    if step <= 0:
        raise ValueError(f"step must be positive, got {step}.")
    if in_sample <= 0 or out_sample <= 0:
        raise ValueError("in_sample and out_sample must be positive.")

    total_needed = in_sample + out_sample
    windows: List[Tuple[int, int, int, int]] = []
    start_idx = 0

    while start_idx + total_needed <= n_days:
        is_start = start_idx
        is_end = start_idx + in_sample - 1
        oos_start = start_idx + in_sample
        oos_end = min(start_idx + total_needed - 1, n_days - 1)
        windows.append((is_start, is_end, oos_start, oos_end))
        start_idx += step

    return windows


def apply_embargo(
    train_idx: Sequence[int], test_idx: Sequence[int], embargo: int
) -> List[int]:
    """
    Drop training indices within ``embargo`` observations of the test
    window's boundaries (both immediately before and immediately after).

    Purpose: adjacent-to-test-set training samples can be correlated with
    the test set through serial correlation (e.g. overlapping rolling
    features), leaking information across the train/test boundary. The
    embargo removes a buffer zone on both sides of the test window.

    Parameters
    ----------
    train_idx : Sequence[int]
        Candidate training indices.
    test_idx : Sequence[int]
        Test indices. Only the min/max are used, so this assumes a single
        contiguous test window.
    embargo : int
        Number of observations to drop immediately before and after the
        test window. Must be non-negative.

    Returns
    -------
    Sorted list of training indices with the embargo zone removed.
    """
    if embargo < 0:
        raise ValueError(f"embargo must be non-negative, got {embargo}.")
    if not test_idx:
        return sorted(train_idx)

    test_start, test_end = min(test_idx), max(test_idx)
    embargo_zone = set(range(test_start - embargo, test_start)) | set(
        range(test_end + 1, test_end + 1 + embargo)
    )
    return sorted(set(train_idx) - embargo_zone)


def embargoed_fold_indices(
    folds: Sequence[Tuple[int, int]], i: int, embargo_periods: int
) -> List[int]:
    """
    Index list for fold ``i`` of a ``contiguous_folds`` split, with
    ``embargo_periods`` observations dropped from each side that borders a
    neighbouring fold.

    Used by ``analytics.overfitting.calculate_kfold_stability`` for its
    purged/embargoed k-fold mode: each fold's own Sharpe is computed on the
    fold alone (there is no separate train set), so the embargo is applied
    directly to the fold's near-boundary observations via two ``apply_embargo``
    calls (one per neighbour) rather than to a train set.

    Parameters
    ----------
    folds : list of (start, end)
        Full ``contiguous_folds(t, n_folds)`` output.
    i : int
        Index of the fold to compute embargoed indices for.
    embargo_periods : int
        Observations dropped from each bordering side. 0 = no-op (returns
        the fold's original ``range(start, end)`` as a list).

    Returns
    -------
    Sorted list of surviving indices for fold ``i``.
    """
    start, end = folds[i]
    fold_idx = list(range(start, end))
    if embargo_periods <= 0:
        return fold_idx
    if i > 0:
        prev_start, prev_end = folds[i - 1]
        fold_idx = apply_embargo(fold_idx, range(prev_start, prev_end), embargo_periods)
    if i < len(folds) - 1:
        next_start, next_end = folds[i + 1]
        fold_idx = apply_embargo(fold_idx, range(next_start, next_end), embargo_periods)
    return fold_idx


def purge(train_idx: Sequence[int], test_idx: Sequence[int], horizon: int) -> List[int]:
    """
    Drop training indices whose label horizon overlaps the test window.

    A training observation at index ``i`` typically has a label computed
    over a forward-looking window ``[i, i + horizon]`` (e.g. a forward
    return over a holding period). If that window overlaps the test set,
    the training label leaks information from the test period and must be
    "purged" from the training set (Lopez de Prado, *Advances in Financial
    Machine Learning*, ch. 7).

    Parameters
    ----------
    train_idx : Sequence[int]
        Candidate training indices.
    test_idx : Sequence[int]
        Test indices. Only the min/max are used, so this assumes a single
        contiguous test window.
    horizon : int
        Label horizon in observations. Must be non-negative.

    Returns
    -------
    Sorted list of training indices with overlapping-horizon rows removed.
    """
    if horizon < 0:
        raise ValueError(f"horizon must be non-negative, got {horizon}.")
    if not test_idx:
        return sorted(train_idx)

    test_start, test_end = min(test_idx), max(test_idx)
    purged = {i for i in train_idx if not (i <= test_end and i + horizon >= test_start)}
    return sorted(purged)
