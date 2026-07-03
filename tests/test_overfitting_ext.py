"""
Tests for Phase 6 overfitting suite extensions: MinBTL, purged/embargoed
k-fold, the honest n_trials map, ``build_family_return_matrix``, and
walk-forward serialisation.

All tests use synthetic data — no IB connection, cached prices, or existing
results/ directory required.
"""

import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from analytics.family_matrix import build_family_return_matrix
from analytics.overfitting import (
    calculate_kfold_stability,
    calculate_minbtl,
)
from analytics.overfitting_results import (
    MinBTLResult,
    walk_forward_to_dict,
)
from backtesting.results_schema import STRATEGY_FILES
from backtesting.results_schema import strategy_dir as schema_strategy_dir
from optimization.splitters import contiguous_folds

# scripts/ has no __init__.py — import it the same way the scripts
# themselves do (sys.path insertion), so build_n_trials_map / PBO_PARAM_GRIDS
# can be tested directly.
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from run_all_overfitting import (  # noqa: E402
    PBO_PARAM_GRIDS,
    build_n_trials_map,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def make_monthly_returns(
    n: int = 60, mean: float = 0.008, std: float = 0.04, seed: int = 42
):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2019-01-31", periods=n, freq="ME")
    return pd.Series(rng.normal(mean, std, n), index=idx, name="returns")


def _write_portfolio_history(results_dir: Path, key: str, dates, values) -> None:
    """Write a synthetic portfolio_history.json for build_family_return_matrix tests."""
    d = schema_strategy_dir(results_dir, key)
    d.mkdir(parents=True, exist_ok=True)
    path = d / STRATEGY_FILES["portfolio_history"]
    data = [
        {"date": str(pd.Timestamp(date).date()), "total_value": float(v)}
        for date, v in zip(dates, values)
    ]
    with open(path, "w") as f:
        json.dump(data, f)


# ---------------------------------------------------------------------------
# MinBTL
# ---------------------------------------------------------------------------


class TestMinBTL:
    def test_result_type(self):
        r = calculate_minbtl(
            observed_sharpe_annualized=1.0, n_trials=5, actual_years=10
        )
        assert isinstance(r, MinBTLResult)

    def test_monotonic_increase_with_n_trials(self):
        """Holding Sharpe fixed, min_years must rise as n_trials rises
        (E[max_N] grows with N)."""
        sr = 1.2
        years_at_n = [
            calculate_minbtl(sr, n_trials=n, actual_years=100).min_years
            for n in (2, 5, 10, 25, 50, 100)
        ]
        assert all(a <= b for a, b in zip(years_at_n, years_at_n[1:]))
        # strictly increasing across this wide a range (not just non-decreasing)
        assert years_at_n[0] < years_at_n[-1]

    def test_inversely_related_to_sharpe_squared(self):
        """Doubling SR should roughly quarter min_years (MinBTL ~ 1/SR^2)."""
        low = calculate_minbtl(1.0, n_trials=10, actual_years=100).min_years
        high = calculate_minbtl(2.0, n_trials=10, actual_years=100).min_years
        # min_years is rounded to 4dp inside calculate_minbtl, so allow a
        # small absolute tolerance rather than requiring exact equality.
        assert high == pytest.approx(low / 4, abs=1e-3)

    def test_verdict_pass_when_actual_meets_minimum(self):
        r = calculate_minbtl(
            observed_sharpe_annualized=1.0, n_trials=5, actual_years=1e9
        )
        assert r.verdict == "PASS"
        assert r.actual_years >= r.min_years

    def test_verdict_warn_within_ratio(self):
        probe = calculate_minbtl(1.0, n_trials=5, actual_years=0)
        min_years = probe.min_years
        r = calculate_minbtl(
            1.0, n_trials=5, actual_years=0.9 * min_years, warn_ratio=0.8
        )
        assert r.verdict == "WARN"

    def test_verdict_fail_below_warn_ratio(self):
        probe = calculate_minbtl(1.0, n_trials=5, actual_years=0)
        min_years = probe.min_years
        r = calculate_minbtl(
            1.0, n_trials=5, actual_years=0.1 * min_years, warn_ratio=0.8
        )
        assert r.verdict == "FAIL"

    def test_strong_sharpe_long_track_record_passes(self):
        """A strong Sharpe over a long track record should comfortably PASS
        even with many trials tested."""
        r = calculate_minbtl(
            observed_sharpe_annualized=1.5, n_trials=20, actual_years=15
        )
        assert r.verdict == "PASS"

    def test_weak_sharpe_many_trials_fails(self):
        """A weak Sharpe with many trials and a short track record should FAIL."""
        r = calculate_minbtl(
            observed_sharpe_annualized=0.15, n_trials=500, actual_years=3
        )
        assert r.verdict == "FAIL"

    def test_non_positive_sharpe_is_infinite_and_fails(self):
        r = calculate_minbtl(
            observed_sharpe_annualized=-0.2, n_trials=5, actual_years=50
        )
        assert math.isinf(r.min_years)
        assert r.verdict == "FAIL"

    def test_n_trials_and_observed_sharpe_stored(self):
        r = calculate_minbtl(observed_sharpe_annualized=0.9, n_trials=7, actual_years=5)
        assert r.n_trials == 7
        assert r.observed_sharpe == pytest.approx(0.9)

    def test_wired_into_run_overfitting_analysis(self):
        from analytics.overfitting import run_overfitting_analysis

        returns = make_monthly_returns(n=60)
        analysis = run_overfitting_analysis(
            strategy_key="minbtl_wire_test",
            strategy_returns=returns,
            return_matrix=None,
            param_grid={},
            n_folds=6,
        )
        assert analysis.minbtl is not None
        assert isinstance(analysis.minbtl, MinBTLResult)
        # T=60 monthly periods -> 5 years
        assert analysis.minbtl.actual_years == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# Purged / embargoed k-fold
# ---------------------------------------------------------------------------


class TestPurgedKFold:
    def test_embargo_zero_reproduces_plain_slicing(self):
        """embargo_periods=0 must exactly match the pre-Phase-6 (plain
        contiguous slice) fold Sharpes."""
        returns = make_monthly_returns(n=60)
        arr = returns.dropna().values
        result = calculate_kfold_stability(returns, n_folds=6, embargo_periods=0)

        expected = []
        for start, end in contiguous_folds(len(arr), 6):
            fold = arr[start:end]
            sr = fold.mean() / fold.std(ddof=1) * math.sqrt(12)
            expected.append(round(sr, 4))

        assert result.fold_sharpes == expected
        assert result.embargo_periods == 0

    def test_embargo_default_is_zero(self):
        returns = make_monthly_returns(n=60)
        r_default = calculate_kfold_stability(returns, n_folds=6)
        r_explicit = calculate_kfold_stability(returns, n_folds=6, embargo_periods=0)
        assert r_default.fold_sharpes == r_explicit.fold_sharpes

    def test_embargo_drops_expected_observations(self):
        """embargo_periods=2 must drop exactly the first/last `embargo`
        observations of each internal fold boundary (interior folds lose
        from both sides, edge folds lose from only their internal side)."""
        n_folds = 3
        t = 30
        embargo = 2
        arr = np.random.default_rng(3).normal(0.01, 0.03, t)
        idx = pd.date_range("2019-01-31", periods=t, freq="ME")
        returns = pd.Series(arr, index=idx)

        result = calculate_kfold_stability(
            returns,
            n_folds=n_folds,
            embargo_periods=embargo,
            threshold_pass=-999,
            threshold_warn=-999,
        )

        folds = contiguous_folds(t, n_folds)
        for i, (start, end) in enumerate(folds):
            lo = start + (embargo if i > 0 else 0)
            hi = end - (embargo if i < len(folds) - 1 else 0)
            expected_fold = arr[lo:hi]
            expected_sr = round(
                expected_fold.mean() / expected_fold.std(ddof=1) * math.sqrt(12), 4
            )
            assert result.fold_sharpes[i] == expected_sr

    def test_embargo_periods_field_stored(self):
        returns = make_monthly_returns(n=60)
        result = calculate_kfold_stability(returns, n_folds=6, embargo_periods=1)
        assert result.embargo_periods == 1

    def test_negative_embargo_raises(self):
        returns = make_monthly_returns(n=60)
        with pytest.raises(ValueError, match="non-negative"):
            calculate_kfold_stability(returns, n_folds=6, embargo_periods=-1)

    def test_embargo_too_large_raises(self):
        """An embargo that consumes an entire (small) fold must raise
        rather than silently produce a degenerate 0/1-observation Sharpe.
        n=30, n_folds=3 -> fold size 10; the interior fold loses embargo
        observations from BOTH sides, so embargo_periods=5 empties it."""
        returns = make_monthly_returns(n=30)
        with pytest.raises(ValueError, match="embargo_periods"):
            calculate_kfold_stability(returns, n_folds=3, embargo_periods=5)

    def test_embargo_changes_result_vs_unembargoed(self):
        returns = make_monthly_returns(n=60)
        r0 = calculate_kfold_stability(returns, n_folds=6, embargo_periods=0)
        r1 = calculate_kfold_stability(returns, n_folds=6, embargo_periods=1)
        assert r0.fold_sharpes != r1.fold_sharpes

    def test_to_dict_includes_embargo_periods(self):
        from analytics.overfitting import run_overfitting_analysis
        from analytics.overfitting_results import overfitting_analysis_to_dict

        returns = make_monthly_returns(n=60)
        analysis = run_overfitting_analysis(
            strategy_key="embargo_dict_test",
            strategy_returns=returns,
            return_matrix=None,
            param_grid={},
            n_folds=6,
            embargo_periods=1,
        )
        d = overfitting_analysis_to_dict(analysis)
        assert d["kfold"]["embargo_periods"] == 1
        assert d["config"]["embargo_periods"] == 1
        json.dumps(d)


# ---------------------------------------------------------------------------
# build_n_trials_map
# ---------------------------------------------------------------------------


class TestBuildNTrialsMap:
    def test_grid_family_uses_cartesian_size(self):
        keys = ["hrp_ward", "hrp_single", "hrp_complete"]
        class_lookup = {k: "HRPStrategy" for k in keys}
        result = build_n_trials_map(keys, class_lookup=class_lookup)
        # hrp grid: linkage_method has 4 values -> cartesian size 4
        expected_n = len(PBO_PARAM_GRIDS["hrp"]["param_grid"]["linkage_method"])
        assert all(v == expected_n for v in result.values())

    def test_trend_following_grid_family_size(self):
        class_lookup = {"trend_following": "TrendFollowingStrategy"}
        result = build_n_trials_map(["trend_following"], class_lookup=class_lookup)
        grid = PBO_PARAM_GRIDS["trend_following"]["param_grid"]
        expected_n = len(grid["lookback_days"]) * len(grid["half_life_days"])
        assert result["trend_following"] == expected_n == 9

    def test_class_grouped_family_counts_siblings(self):
        keys = ["custom_a", "custom_b", "custom_c"]
        class_lookup = {k: "CustomStrategy" for k in keys}
        result = build_n_trials_map(keys, class_lookup=class_lookup)
        assert all(v == 3 for v in result.values())

    def test_singleton_class_floors_at_2(self):
        result = build_n_trials_map(
            ["lonely_strategy"], class_lookup={"lonely_strategy": "LonelyClass"}
        )
        assert result["lonely_strategy"] == 2

    def test_does_not_lump_different_classes_sharing_prefix_token(self):
        """Regression test: trend_following / trend_signal_rp /
        trend_signal_mvo share a "trend" prefix TOKEN but are different
        strategy classes and must not be treated as siblings."""
        keys = ["trend_following", "trend_signal_rp", "trend_signal_mvo"]
        class_lookup = {
            "trend_following": "TrendFollowingStrategy",
            "trend_signal_rp": "TrendSignalRPStrategy",
            "trend_signal_mvo": "TrendSignalMVOStrategy",
        }
        result = build_n_trials_map(keys, class_lookup=class_lookup)
        assert result["trend_following"] == 9  # matches PBO grid family
        # each of these is a singleton class among the given keys -> floor 2,
        # NOT 3 (the old prefix-based bug would have given all three N=3).
        assert result["trend_signal_rp"] == 2
        assert result["trend_signal_mvo"] == 2

    def test_mixed_grid_and_class_grouped_keys(self):
        keys = ["hrp_ward", "hrp_single", "my_custom_strategy", "my_custom_strategy_2"]
        class_lookup = {
            "hrp_ward": "HRPStrategy",
            "hrp_single": "HRPStrategy",
            "my_custom_strategy": "MyCustomStrategy",
            "my_custom_strategy_2": "MyCustomStrategy",
        }
        result = build_n_trials_map(keys, class_lookup=class_lookup)
        hrp_n = len(PBO_PARAM_GRIDS["hrp"]["param_grid"]["linkage_method"])
        assert result["hrp_ward"] == hrp_n
        assert result["hrp_single"] == hrp_n
        assert result["my_custom_strategy"] == 2
        assert result["my_custom_strategy_2"] == 2

    def test_key_prefix_match_without_class_match_falls_back_to_class_grouping(self):
        """A key sharing a PBO_PARAM_GRIDS family's name PREFIX but with a
        different class must NOT get the grid's n_trials."""
        keys = ["hrp_15vol"]
        # hrp_15vol is a composed/overlay strategy, not an HRPStrategy itself
        class_lookup = {"hrp_15vol": "VolatilityTargetStrategy"}
        result = build_n_trials_map(keys, class_lookup=class_lookup)
        assert result["hrp_15vol"] == 2  # floor, singleton class, NOT the hrp grid size


# ---------------------------------------------------------------------------
# build_family_return_matrix
# ---------------------------------------------------------------------------


class TestBuildFamilyReturnMatrix:
    def test_shape_and_alignment(self, tmp_path):
        dates = pd.date_range("2020-01-31", periods=10, freq="ME")
        rng = np.random.default_rng(5)
        for key in ("a", "b", "c", "d"):
            values = 100 * np.cumprod(1 + rng.normal(0.01, 0.02, 10))
            _write_portfolio_history(tmp_path, key, dates, values)

        matrix = build_family_return_matrix(tmp_path, ["a", "b", "c", "d"])
        assert isinstance(matrix, pd.DataFrame)
        assert matrix.shape == (9, 4)  # pct_change drops first row
        assert list(matrix.columns) == ["a", "b", "c", "d"]
        assert matrix.index.is_monotonic_increasing

    def test_inner_join_on_misaligned_dates(self, tmp_path):
        dates_a = pd.date_range("2020-01-31", periods=10, freq="ME")
        dates_b = pd.date_range(
            "2020-03-31", periods=10, freq="ME"
        )  # shifted, less overlap
        rng = np.random.default_rng(6)
        _write_portfolio_history(
            tmp_path, "a", dates_a, 100 * np.cumprod(1 + rng.normal(0.01, 0.02, 10))
        )
        _write_portfolio_history(
            tmp_path, "b", dates_b, 100 * np.cumprod(1 + rng.normal(0.01, 0.02, 10))
        )

        matrix = build_family_return_matrix(tmp_path, ["a", "b"])
        # Only overlapping dates (both series' dates present) should survive.
        assert set(matrix.index).issubset(set(dates_a) & set(dates_b))
        assert not matrix.isna().any().any()

    def test_missing_sibling_handled_gracefully(self, tmp_path):
        dates = pd.date_range("2020-01-31", periods=10, freq="ME")
        rng = np.random.default_rng(7)
        for key in ("a", "b", "c"):
            values = 100 * np.cumprod(1 + rng.normal(0.01, 0.02, 10))
            _write_portfolio_history(tmp_path, key, dates, values)
        # "missing" has no portfolio_history.json on disk at all.

        matrix = build_family_return_matrix(tmp_path, ["a", "b", "c", "missing"])
        assert list(matrix.columns) == ["a", "b", "c"]
        assert matrix.shape[0] == 9

    def test_all_missing_returns_empty_dataframe(self, tmp_path):
        matrix = build_family_return_matrix(tmp_path, ["nope1", "nope2"])
        assert isinstance(matrix, pd.DataFrame)
        assert matrix.empty

    def test_returned_matrix_is_pct_change(self, tmp_path):
        dates = pd.date_range("2020-01-31", periods=5, freq="ME")
        values = [100.0, 110.0, 121.0, 133.1, 146.41]  # +10% each period
        _write_portfolio_history(tmp_path, "steady", dates, values)
        _write_portfolio_history(tmp_path, "steady2", dates, values)

        matrix = build_family_return_matrix(tmp_path, ["steady", "steady2"])
        assert matrix["steady"].values == pytest.approx([0.10] * 4, abs=1e-6)


# ---------------------------------------------------------------------------
# walk_forward_to_dict
# ---------------------------------------------------------------------------


def _make_wf_results(
    avg_in: float, avg_out: float, n_windows: int, target_metric="sharpe_ratio"
):
    ratio = avg_in / avg_out if avg_out != 0 else float("inf")
    return SimpleNamespace(
        avg_in_sample=avg_in,
        avg_out_sample=avg_out,
        overfitting_ratio=ratio,
        windows=[object()] * n_windows,
        target_metric=target_metric,
    )


class TestWalkForwardToDict:
    def test_pass_verdict_below_1_5(self):
        wf = _make_wf_results(1.0, 0.8, 4)  # ratio = 1.25
        d = walk_forward_to_dict(wf)
        assert d["verdict"] == "PASS"
        assert d["overfitting_ratio"] == pytest.approx(1.25)
        assert d["n_windows"] == 4
        assert d["target_metric"] == "sharpe_ratio"

    def test_warn_verdict_between_1_5_and_2_5(self):
        wf = _make_wf_results(2.0, 1.0, 3)  # ratio = 2.0
        d = walk_forward_to_dict(wf)
        assert d["verdict"] == "WARN"

    def test_fail_verdict_above_2_5(self):
        wf = _make_wf_results(3.0, 1.0, 3)  # ratio = 3.0
        d = walk_forward_to_dict(wf)
        assert d["verdict"] == "FAIL"

    def test_pass_boundary_is_exclusive(self):
        wf = _make_wf_results(1.5, 1.0, 2)  # ratio == 1.5 exactly -> not PASS
        d = walk_forward_to_dict(wf)
        assert d["verdict"] == "WARN"

    def test_warn_boundary_is_exclusive(self):
        wf = _make_wf_results(2.5, 1.0, 2)  # ratio == 2.5 exactly -> not WARN
        d = walk_forward_to_dict(wf)
        assert d["verdict"] == "FAIL"

    def test_inf_guard_when_avg_out_sample_zero(self):
        wf = _make_wf_results(1.0, 0.0, 2)
        d = walk_forward_to_dict(wf)
        assert d["overfitting_ratio"] is None
        assert d["verdict"] == "FAIL"
        # Must be JSON-safe (no literal Infinity token).
        serialised = json.dumps(d)
        assert "Infinity" not in serialised

    def test_dict_is_json_serializable(self):
        wf = _make_wf_results(1.2, 1.0, 5)
        d = walk_forward_to_dict(wf)
        serialised = json.dumps(d)
        assert "sharpe_ratio" in serialised
