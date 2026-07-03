"""
Tests for optimization/splitters.py — pure time-series index-splitting
utilities used by k-fold temporal stability analysis, walk-forward
analysis, and (in later phases) embargoed/purged cross-validation.
"""

import numpy as np
import pandas as pd
import pytest

from optimization.splitters import (
    apply_embargo,
    contiguous_folds,
    purge,
    rolling_windows,
)

# ---------------------------------------------------------------------------
# contiguous_folds
# ---------------------------------------------------------------------------


class TestContiguousFolds:

    def test_evenly_divisible(self):
        """T divides evenly by n_folds: no residual, folds tile [0, T)."""
        folds = contiguous_folds(t=12, n_folds=4)
        assert folds == [(0, 3), (3, 6), (6, 9), (9, 12)]

    def test_unevenly_divisible_residual_discarded(self):
        """T does not divide evenly: leading residual rows are dropped."""
        folds = contiguous_folds(t=10, n_folds=3)
        # residual = 10 % 3 = 1, fold_size = 3 -> first fold starts at index 1
        assert folds == [(1, 4), (4, 7), (7, 10)]

    def test_fold_count_matches_n_folds(self):
        folds = contiguous_folds(t=100, n_folds=10)
        assert len(folds) == 10

    def test_folds_are_equal_size(self):
        folds = contiguous_folds(t=97, n_folds=7)
        sizes = {end - start for start, end in folds}
        assert len(sizes) == 1  # all folds the same size

    def test_folds_cover_exactly_t_minus_residual_rows(self):
        t, n_folds = 97, 7
        residual = t % n_folds
        folds = contiguous_folds(t=t, n_folds=n_folds)
        assert folds[0][0] == residual
        assert folds[-1][1] == t

    def test_matches_old_kfold_residual_behavior(self):
        """
        Reproduces the exact indexing previously inlined in
        calculate_kfold_stability: trim the leading residual from the
        array, then slice fold_size chunks starting at 0.
        """
        rng = np.random.default_rng(0)
        t = 97
        n_folds = 7
        arr = rng.normal(size=t)

        residual = t % n_folds
        trimmed = arr[residual:] if residual else arr
        fold_size = len(trimmed) // n_folds
        expected_folds = [
            trimmed[i * fold_size : (i + 1) * fold_size] for i in range(n_folds)
        ]

        folds = contiguous_folds(t, n_folds)
        actual_folds = [arr[start:end] for start, end in folds]

        for expected, actual in zip(expected_folds, actual_folds):
            np.testing.assert_array_equal(expected, actual)

    def test_no_residual_when_evenly_divisible(self):
        folds = contiguous_folds(t=20, n_folds=5)
        assert folds[0][0] == 0

    def test_zero_folds_raises(self):
        with pytest.raises(ValueError, match="positive"):
            contiguous_folds(t=10, n_folds=0)

    def test_negative_folds_raises(self):
        with pytest.raises(ValueError, match="positive"):
            contiguous_folds(t=10, n_folds=-1)

    def test_t_less_than_n_folds_raises(self):
        with pytest.raises(ValueError, match=">="):
            contiguous_folds(t=3, n_folds=5)

    def test_single_fold(self):
        folds = contiguous_folds(t=10, n_folds=1)
        assert folds == [(0, 10)]


# ---------------------------------------------------------------------------
# rolling_windows
# ---------------------------------------------------------------------------


class TestRollingWindows:

    def test_basic_windows(self):
        windows = rolling_windows(n_days=10, in_sample=4, out_sample=2, step=2)
        assert windows == [(0, 3, 4, 5), (2, 5, 6, 7), (4, 7, 8, 9)]

    def test_window_count(self):
        # total_needed = 6; start indices 0,2,4 fit within 10 days -> 3 windows
        windows = rolling_windows(n_days=10, in_sample=4, out_sample=2, step=2)
        assert len(windows) == 3

    def test_windows_are_contiguous_is_then_oos(self):
        for is_start, is_end, oos_start, oos_end in rolling_windows(
            n_days=20, in_sample=5, out_sample=3, step=3
        ):
            assert oos_start == is_end + 1
            assert oos_end >= oos_start

    def test_step_larger_than_window_leaves_gaps(self):
        windows = rolling_windows(n_days=20, in_sample=2, out_sample=2, step=6)
        starts = [w[0] for w in windows]
        assert starts == sorted(starts)
        assert all(b - a == 6 for a, b in zip(starts, starts[1:]))

    def test_no_windows_when_insufficient_days(self):
        windows = rolling_windows(n_days=5, in_sample=4, out_sample=4, step=1)
        assert windows == []

    def test_last_window_oos_end_capped_at_n_days_minus_one(self):
        windows = rolling_windows(n_days=10, in_sample=4, out_sample=2, step=2)
        for _, _, _, oos_end in windows:
            assert oos_end <= 9

    def test_exact_fit_single_window(self):
        windows = rolling_windows(n_days=6, in_sample=4, out_sample=2, step=2)
        assert windows == [(0, 3, 4, 5)]

    def test_non_positive_step_raises(self):
        with pytest.raises(ValueError, match="step"):
            rolling_windows(n_days=10, in_sample=4, out_sample=2, step=0)

    def test_non_positive_in_sample_raises(self):
        with pytest.raises(ValueError):
            rolling_windows(n_days=10, in_sample=0, out_sample=2, step=1)

    def test_matches_walk_forward_index_semantics(self):
        """
        Reproduces the original inline while-loop from WalkForwardAnalysis.run
        and checks index-for-index equivalence.
        """
        n_days, in_sample, out_sample, step = 30, 10, 5, 5
        total_needed = in_sample + out_sample

        expected = []
        start_idx = 0
        while start_idx + total_needed <= n_days:
            is_start = start_idx
            is_end = start_idx + in_sample - 1
            oos_start = start_idx + in_sample
            oos_end = min(start_idx + total_needed - 1, n_days - 1)
            expected.append((is_start, is_end, oos_start, oos_end))
            start_idx += step

        assert rolling_windows(n_days, in_sample, out_sample, step) == expected


# ---------------------------------------------------------------------------
# apply_embargo
# ---------------------------------------------------------------------------


class TestApplyEmbargo:

    def test_drops_embargo_zone_on_both_sides(self):
        train = list(range(0, 20))
        test = [10, 11, 12]
        result = apply_embargo(train, test, embargo=2)
        # Should drop 8,9 (before) and 13,14 (after)
        assert 8 not in result and 9 not in result
        assert 13 not in result and 14 not in result
        # Test indices themselves were never in train, unaffected
        assert 7 in result
        assert 15 in result

    def test_zero_embargo_no_change(self):
        train = list(range(0, 10))
        test = [5]
        result = apply_embargo(train, test, embargo=0)
        assert result == sorted(train)

    def test_embargo_only_removes_present_indices(self):
        """Embargo zone drops the buffer on both sides; unrelated indices
        (including the test index itself, if present in train_idx) are
        left untouched — apply_embargo only ever removes the adjacent
        buffer, not the test window."""
        train = [0, 1, 2, 3, 4]
        test = [2]
        result = apply_embargo(train, test, embargo=1)
        assert 1 not in result
        assert 3 not in result
        assert result == [0, 2, 4]

    def test_empty_test_idx_returns_sorted_train(self):
        train = [3, 1, 2]
        assert apply_embargo(train, [], embargo=5) == [1, 2, 3]

    def test_negative_embargo_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            apply_embargo([1, 2, 3], [2], embargo=-1)

    def test_result_is_sorted(self):
        train = [9, 1, 5, 0, 20]
        result = apply_embargo(train, [50], embargo=1)
        assert result == sorted(result)


# ---------------------------------------------------------------------------
# purge
# ---------------------------------------------------------------------------


class TestPurge:

    def test_drops_train_rows_whose_horizon_overlaps_test(self):
        train = list(range(0, 10))
        test = [8, 9]
        # horizon=2: rows i with i<=9 and i+2>=8 -> i in [6,7] purged (already
        # excludes 8,9 since they aren't in train)
        result = purge(train, test, horizon=2)
        assert 6 not in result
        assert 7 not in result
        assert 5 in result

    def test_zero_horizon_only_purges_rows_at_or_before_test_start(self):
        train = list(range(0, 10))
        test = [5, 6]
        result = purge(train, test, horizon=0)
        # horizon=0: purge condition is i <= test_end and i >= test_start
        # i.e. i in [5, 6] -- neither is in train (train stops at 9, but
        # 5 and 6 ARE in train here) so they get purged.
        assert 5 not in result
        assert 6 not in result
        assert 4 in result
        assert 7 in result

    def test_empty_test_idx_returns_sorted_train(self):
        train = [5, 3, 4]
        assert purge(train, [], horizon=3) == [3, 4, 5]

    def test_negative_horizon_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            purge([1, 2, 3], [2], horizon=-1)

    def test_result_is_sorted(self):
        train = [9, 1, 5, 0, 20]
        result = purge(train, [50], horizon=1)
        assert result == sorted(result)

    def test_large_horizon_purges_far_preceding_rows(self):
        train = list(range(0, 20))
        test = [15]
        result = purge(train, test, horizon=10)
        # i + 10 >= 15 -> i >= 5; i <= 15 (test_end) -> rows [5..15] purged
        for i in range(5, 16):
            assert i not in result
        assert 4 in result
