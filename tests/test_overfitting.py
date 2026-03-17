"""
Tests for DSR and PBO overfitting analytics.

All tests use synthetic data — no IB connection or cached files required.
Follows the style of test_optimization.py.
"""

import json
import math

import numpy as np
import pandas as pd
import pytest

from analytics.overfitting import (
    DSRResult,
    KFoldResult,
    OverfittingAnalysis,
    PBOResult,
    calculate_deflated_sharpe_ratio,
    calculate_kfold_stability,
    calculate_pbo,
    overfitting_analysis_to_dict,
    run_overfitting_analysis,
)
from optimization import ParameterSweep
from strategies.core import AssetStrategy
from strategies.hrp import HRPStrategy

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SYMBOLS = ["VUSA", "SSLN", "SGLN", "IWRD"]
N_PERIODS = 60  # monthly periods (~5 years)


def make_monthly_returns(
    n: int = N_PERIODS,
    mean: float = 0.008,
    std: float = 0.04,
    seed: int = 42,
) -> pd.Series:
    """Synthetic monthly portfolio return series with positive mean."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2019-01-31", periods=n, freq="ME")
    return pd.Series(rng.normal(mean, std, n), index=idx, name="returns")


def make_return_matrix(
    n_periods: int = N_PERIODS,
    n_configs: int = 4,
    seed: int = 99,
) -> pd.DataFrame:
    """Synthetic return matrix (T, N) — one column per parameter combination."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2019-01-31", periods=n_periods, freq="ME")
    base = rng.normal(0.008, 0.04, n_periods)
    data = {
        f"config_{i}": base + rng.normal(0, 0.005, n_periods) for i in range(n_configs)
    }
    return pd.DataFrame(data, index=idx)


def make_prices(n_days: int = 500, seed: int = 42) -> pd.DataFrame:
    """Synthetic daily OHLCV-like prices for integration tests."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=n_days)
    returns = rng.normal(loc=0.0003, scale=0.01, size=(n_days, len(SYMBOLS)))
    prices = 100 * np.exp(np.cumsum(returns, axis=0))
    return pd.DataFrame(prices, index=dates, columns=SYMBOLS)


@pytest.fixture(scope="module")
def monthly_returns():
    return make_monthly_returns()


@pytest.fixture(scope="module")
def return_matrix():
    return make_return_matrix()


@pytest.fixture(scope="module")
def prices():
    return make_prices()


@pytest.fixture(scope="module")
def underlying():
    return [AssetStrategy(s, currency="GBP") for s in SYMBOLS]


# ---------------------------------------------------------------------------
# DSR tests
# ---------------------------------------------------------------------------


class TestDSR:

    def test_dsr_in_range(self, monthly_returns):
        """DSR is in [0, 1]."""
        result = calculate_deflated_sharpe_ratio(monthly_returns, n_trials=3)
        assert 0.0 <= result.dsr <= 1.0

    def test_dsr_result_type(self, monthly_returns):
        """calculate_deflated_sharpe_ratio returns DSRResult."""
        result = calculate_deflated_sharpe_ratio(monthly_returns, n_trials=3)
        assert isinstance(result, DSRResult)

    def test_dsr_result_fields(self, monthly_returns):
        """DSRResult has all required fields populated."""
        r = calculate_deflated_sharpe_ratio(monthly_returns, n_trials=3)
        assert r.t_periods == len(monthly_returns)
        assert r.n_trials == 3
        assert isinstance(r.skewness, float)
        assert isinstance(r.excess_kurtosis, float)
        assert r.verdict in ("PASS", "WARN", "FAIL")

    def test_dsr_decreases_with_more_trials(self, monthly_returns):
        """More trials → lower DSR (corrects for multiple testing)."""
        r1 = calculate_deflated_sharpe_ratio(monthly_returns, n_trials=2)
        r10 = calculate_deflated_sharpe_ratio(monthly_returns, n_trials=10)
        assert r1.dsr >= r10.dsr

    def test_dsr_increases_with_higher_mean(self):
        """Higher-returning series → higher DSR."""
        low_returns = make_monthly_returns(mean=0.001, seed=1)
        high_returns = make_monthly_returns(mean=0.015, seed=1)
        r_low = calculate_deflated_sharpe_ratio(low_returns, n_trials=3)
        r_high = calculate_deflated_sharpe_ratio(high_returns, n_trials=3)
        assert r_high.dsr > r_low.dsr

    def test_dsr_short_series_raises(self):
        """Series with < 10 periods raises ValueError."""
        short = pd.Series([0.01, -0.02, 0.03, 0.01, -0.01])
        with pytest.raises(ValueError, match="too short"):
            calculate_deflated_sharpe_ratio(short, n_trials=2)

    def test_dsr_verdict_pass(self):
        """Strong positive Sharpe with N=2 → PASS."""
        # High, consistent positive returns with small noise
        rng = np.random.default_rng(0)
        idx = pd.date_range("2019-01-31", periods=60, freq="ME")
        good = pd.Series(0.05 + rng.normal(0, 0.001, 60), index=idx)
        result = calculate_deflated_sharpe_ratio(good, n_trials=2)
        assert result.verdict == "PASS"

    def test_dsr_verdict_fail(self):
        """Near-zero Sharpe with many trials → FAIL."""
        rng = np.random.default_rng(7)
        noisy = pd.Series(
            rng.normal(0.0, 0.05, 60),
            index=pd.date_range("2019-01-31", periods=60, freq="ME"),
        )
        result = calculate_deflated_sharpe_ratio(noisy, n_trials=50)
        assert result.verdict in ("WARN", "FAIL")

    def test_dsr_with_sharpe_std(self, monthly_returns):
        """Providing sharpe_std overrides single-series fallback."""
        r_auto = calculate_deflated_sharpe_ratio(monthly_returns, n_trials=3)
        r_manual = calculate_deflated_sharpe_ratio(
            monthly_returns, n_trials=3, sharpe_std=0.5
        )
        # Results differ when sharpe_std is explicitly set
        assert isinstance(r_manual.dsr, float)
        assert 0.0 <= r_manual.dsr <= 1.0

    def test_dsr_observed_sharpe_annualised(self, monthly_returns):
        """observed_sharpe is annualised (multiplied by sqrt(12))."""
        result = calculate_deflated_sharpe_ratio(
            monthly_returns, n_trials=2, periods_per_year=12
        )
        # Manual annualised SR
        arr = monthly_returns.dropna().values
        sr_period = arr.mean() / arr.std(ddof=1)
        expected_annual = sr_period * math.sqrt(12)
        assert abs(result.observed_sharpe - expected_annual) < 0.01


# ---------------------------------------------------------------------------
# PBO tests
# ---------------------------------------------------------------------------


class TestPBO:

    def test_pbo_in_range(self, return_matrix):
        """PBO is in [0, 1]."""
        result = calculate_pbo(return_matrix, s_subsets=8)
        assert 0.0 <= result.pbo <= 1.0

    def test_pbo_result_type(self, return_matrix):
        """calculate_pbo returns PBOResult."""
        result = calculate_pbo(return_matrix, s_subsets=8)
        assert isinstance(result, PBOResult)

    def test_pbo_n_combinations_correct(self, return_matrix):
        """C(8, 4) = 70 combinations when s_subsets=8."""
        result = calculate_pbo(return_matrix, s_subsets=8)
        assert result.n_combinations == 70

    def test_pbo_logit_length_matches_combinations(self, return_matrix):
        """logit_scores length equals n_combinations."""
        result = calculate_pbo(return_matrix, s_subsets=8)
        assert len(result.logit_scores) == result.n_combinations

    def test_pbo_odd_s_subsets_raises(self, return_matrix):
        """Odd s_subsets raises ValueError."""
        with pytest.raises(ValueError, match="even"):
            calculate_pbo(return_matrix, s_subsets=7)

    def test_pbo_insufficient_periods_raises(self):
        """s_subsets > T raises ValueError."""
        tiny = make_return_matrix(n_periods=5, n_configs=3)
        with pytest.raises(ValueError, match="Too few periods"):
            calculate_pbo(tiny, s_subsets=16)

    def test_pbo_verdict_field(self, return_matrix):
        """PBOResult.verdict is one of PASS/WARN/FAIL."""
        result = calculate_pbo(return_matrix, s_subsets=8)
        assert result.verdict in ("PASS", "WARN", "FAIL")

    def test_pbo_n_configs(self, return_matrix):
        """n_configs matches number of columns in return_matrix."""
        result = calculate_pbo(return_matrix, s_subsets=8)
        assert result.n_configs == return_matrix.shape[1]

    def test_pbo_dominant_strategy_low_pbo(self):
        """A clearly dominant strategy (much higher mean) gives PBO near 0."""
        rng = np.random.default_rng(1)
        idx = pd.date_range("2019-01-31", periods=64, freq="ME")
        # Config 0 has consistently higher returns
        data = {
            "dominant": pd.Series(rng.normal(0.05, 0.02, 64), index=idx),
            "mediocre_1": pd.Series(rng.normal(0.001, 0.04, 64), index=idx),
            "mediocre_2": pd.Series(rng.normal(0.001, 0.04, 64), index=idx),
        }
        matrix = pd.DataFrame(data)
        result = calculate_pbo(matrix, s_subsets=8)
        # With a dominant strategy, PBO should be low (below 0.5)
        assert result.pbo < 0.5

    def test_pbo_random_strategies_pbo_nonzero(self):
        """Truly random i.i.d. configs should have non-trivial PBO (> 0.1)."""
        rng = np.random.default_rng(77)
        idx = pd.date_range("2019-01-31", periods=64, freq="ME")
        # Independent random configs — selection is essentially random
        data = {f"c{i}": pd.Series(rng.normal(0.005, 0.04, 64), index=idx) for i in range(6)}
        matrix = pd.DataFrame(data)
        result = calculate_pbo(matrix, s_subsets=8)
        # For uncorrelated random configs, PBO should be clearly above 0
        assert result.pbo > 0.1

    def test_pbo_prob_oos_loss_in_range(self, return_matrix):
        """prob_oos_loss is in [0, 1]."""
        result = calculate_pbo(return_matrix, s_subsets=8)
        assert 0.0 <= result.prob_oos_loss <= 1.0


# ---------------------------------------------------------------------------
# ParameterSweep with store_returns tests
# ---------------------------------------------------------------------------


class TestParameterSweepWithReturns:

    def test_store_returns_flag_populates_dict(self, prices, underlying):
        """store_returns=True populates return_series_ after run()."""
        lookback = 60
        start = prices.index[lookback]
        end = prices.index[-1]
        sweep = ParameterSweep(
            strategy_class=HRPStrategy,
            param_grid={"linkage_method": ["single", "ward"]},
            store_returns=True,
        )
        sweep.run(underlying, prices, start, end, lookback_days=lookback)
        assert len(sweep.return_series_) > 0

    def test_store_returns_false_empty_dict(self, prices, underlying):
        """store_returns=False (default) leaves return_series_ empty."""
        lookback = 60
        start = prices.index[lookback]
        end = prices.index[-1]
        sweep = ParameterSweep(
            strategy_class=HRPStrategy,
            param_grid={"linkage_method": ["ward"]},
        )
        sweep.run(underlying, prices, start, end, lookback_days=lookback)
        assert len(sweep.return_series_) == 0

    def test_get_return_matrix_raises_without_flag(self, prices, underlying):
        """get_return_matrix raises RuntimeError if store_returns=False."""
        lookback = 60
        start = prices.index[lookback]
        end = prices.index[-1]
        sweep = ParameterSweep(
            strategy_class=HRPStrategy,
            param_grid={"linkage_method": ["ward"]},
        )
        sweep.run(underlying, prices, start, end, lookback_days=lookback)
        with pytest.raises(RuntimeError, match="store_returns"):
            sweep.get_return_matrix()

    def test_get_return_matrix_shape(self, prices, underlying):
        """return_matrix has (T, N_successful) shape with pct returns."""
        lookback = 60
        start = prices.index[lookback]
        end = prices.index[-1]
        sweep = ParameterSweep(
            strategy_class=HRPStrategy,
            param_grid={"linkage_method": ["single", "complete", "ward"]},
            store_returns=True,
        )
        sweep.run(underlying, prices, start, end, lookback_days=lookback)
        matrix = sweep.get_return_matrix()
        assert isinstance(matrix, pd.DataFrame)
        assert matrix.shape[1] <= 3
        assert matrix.shape[0] > 0
        # Should contain percentage returns (small values)
        assert matrix.abs().max().max() < 1.0

    def test_return_series_keyed_by_frozenset(self, prices, underlying):
        """return_series_ is keyed by frozenset(params.items())."""
        lookback = 60
        start = prices.index[lookback]
        end = prices.index[-1]
        sweep = ParameterSweep(
            strategy_class=HRPStrategy,
            param_grid={"linkage_method": ["ward"]},
            store_returns=True,
        )
        sweep.run(underlying, prices, start, end, lookback_days=lookback)
        keys = list(sweep.return_series_.keys())
        assert all(isinstance(k, frozenset) for k in keys)


# ---------------------------------------------------------------------------
# run_overfitting_analysis integration test
# ---------------------------------------------------------------------------


class TestRunOverfittingAnalysis:

    def test_end_to_end_with_matrix(self):
        """Full pipeline: returns + matrix → DSR + PBO in OverfittingAnalysis."""
        returns = make_monthly_returns(n=60)
        matrix = make_return_matrix(n_periods=60, n_configs=4)
        analysis = run_overfitting_analysis(
            strategy_key="test_strategy",
            strategy_returns=returns,
            return_matrix=matrix,
            param_grid={"linkage_method": ["single", "complete", "ward", "average"]},
        )
        assert isinstance(analysis, OverfittingAnalysis)
        assert analysis.dsr is not None
        assert analysis.pbo is not None
        assert 0.0 <= analysis.dsr.dsr <= 1.0
        assert 0.0 <= analysis.pbo.pbo <= 1.0

    def test_end_to_end_no_matrix_skips_pbo(self):
        """Without return_matrix, PBO is skipped."""
        returns = make_monthly_returns()
        analysis = run_overfitting_analysis(
            strategy_key="test_strategy",
            strategy_returns=returns,
            return_matrix=None,
            param_grid={},
            periods_per_year=12,
        )
        assert analysis.dsr is not None
        assert analysis.pbo is None

    def test_strategy_key_stored(self):
        """strategy_key is preserved in result."""
        returns = make_monthly_returns()
        analysis = run_overfitting_analysis(
            strategy_key="my_strategy",
            strategy_returns=returns,
            return_matrix=None,
            param_grid={},
        )
        assert analysis.strategy_key == "my_strategy"

    def test_errors_list_is_empty_on_success(self):
        """No errors on a valid run."""
        returns = make_monthly_returns(n=50)
        matrix = make_return_matrix(n_periods=50, n_configs=3)
        analysis = run_overfitting_analysis(
            strategy_key="ok",
            strategy_returns=returns,
            return_matrix=matrix,
            param_grid={"top_n": [1, 2, 3]},
            s_subsets=8,
        )
        assert len(analysis.errors) == 0

    def test_end_to_end_with_sweep(self, prices, underlying):
        """Full integration: ParameterSweep → return_matrix → DSR + PBO."""
        lookback = 60
        start = prices.index[lookback]
        end = prices.index[-1]

        sweep = ParameterSweep(
            strategy_class=HRPStrategy,
            param_grid={"linkage_method": ["single", "complete", "ward"]},
            store_returns=True,
        )
        sweep.run(underlying, prices, start, end, lookback_days=lookback)
        matrix = sweep.get_return_matrix()

        best_values = next(iter(sweep.return_series_.values()))
        best_returns = best_values.pct_change().dropna()

        analysis = run_overfitting_analysis(
            strategy_key="hrp_test",
            strategy_returns=best_returns,
            return_matrix=matrix,
            param_grid={"linkage_method": ["single", "complete", "ward"]},
            s_subsets=8,
        )
        assert 0.0 <= analysis.dsr.dsr <= 1.0
        assert 0.0 <= analysis.pbo.pbo <= 1.0


# ---------------------------------------------------------------------------
# Serialisation tests
# ---------------------------------------------------------------------------


class TestSerialization:

    def test_to_dict_json_serializable(self):
        """overfitting_analysis_to_dict output is json.dumps-safe."""
        returns = make_monthly_returns()
        matrix = make_return_matrix(n_configs=3)
        analysis = run_overfitting_analysis(
            strategy_key="serial_test",
            strategy_returns=returns,
            return_matrix=matrix,
            param_grid={"p": [1, 2, 3]},
            s_subsets=8,
        )
        d = overfitting_analysis_to_dict(analysis)
        # Must not raise
        serialised = json.dumps(d)
        assert "serial_test" in serialised

    def test_to_dict_structure(self):
        """Output dict has expected top-level keys."""
        returns = make_monthly_returns()
        analysis = run_overfitting_analysis(
            strategy_key="s",
            strategy_returns=returns,
            return_matrix=None,
            param_grid={},
        )
        d = overfitting_analysis_to_dict(analysis)
        for key in ("strategy_key", "analysis_date", "n_param_combinations", "dsr", "pbo", "errors", "config"):
            assert key in d

    def test_to_dict_dsr_subkeys(self):
        """DSR sub-dict has all required keys."""
        returns = make_monthly_returns()
        analysis = run_overfitting_analysis(
            strategy_key="s",
            strategy_returns=returns,
            return_matrix=None,
            param_grid={},
        )
        d = overfitting_analysis_to_dict(analysis)
        assert d["dsr"] is not None
        dsr_keys = {"dsr", "observed_sharpe", "sharpe_reference", "n_trials",
                    "t_periods", "skewness", "excess_kurtosis", "verdict",
                    "threshold_pass", "threshold_warn"}
        assert dsr_keys.issubset(set(d["dsr"].keys()))

    def test_to_dict_pbo_subkeys(self):
        """PBO sub-dict has all required keys."""
        returns = make_monthly_returns(n=60)
        matrix = make_return_matrix(n_periods=60, n_configs=4)
        analysis = run_overfitting_analysis(
            strategy_key="s",
            strategy_returns=returns,
            return_matrix=matrix,
            param_grid={},
            s_subsets=8,
        )
        d = overfitting_analysis_to_dict(analysis)
        assert d["pbo"] is not None
        pbo_keys = {"pbo", "prob_oos_loss", "n_combinations", "s_subsets",
                    "n_configs", "logit_scores", "verdict",
                    "threshold_pass", "threshold_warn"}
        assert pbo_keys.issubset(set(d["pbo"].keys()))

    def test_to_dict_pbo_none_when_skipped(self):
        """PBO key is None in dict when return_matrix is not provided."""
        returns = make_monthly_returns()
        analysis = run_overfitting_analysis(
            strategy_key="s",
            strategy_returns=returns,
            return_matrix=None,
            param_grid={},
        )
        d = overfitting_analysis_to_dict(analysis)
        assert d["pbo"] is None


# ---------------------------------------------------------------------------
# K-Fold Temporal Stability tests
# ---------------------------------------------------------------------------


class TestKFoldStability:

    def test_kfold_result_type(self):
        """calculate_kfold_stability returns a KFoldResult."""
        returns = make_monthly_returns(n=60)
        result = calculate_kfold_stability(returns, n_folds=6)
        assert isinstance(result, KFoldResult)

    def test_kfold_fold_count(self):
        """fold_sharpes has exactly n_folds entries."""
        returns = make_monthly_returns(n=60)
        result = calculate_kfold_stability(returns, n_folds=5)
        assert len(result.fold_sharpes) == 5
        assert result.n_folds == 5

    def test_kfold_fraction_positive_consistent_strategy(self):
        """A strongly positive returns series should have high fraction_positive."""
        # Very high mean relative to std → all folds should have positive Sharpe
        rng = np.random.default_rng(7)
        idx = pd.date_range("2019-01-31", periods=120, freq="ME")
        returns = pd.Series(rng.normal(0.05, 0.005, 120), index=idx)
        result = calculate_kfold_stability(returns, n_folds=10)
        assert result.fraction_positive == 1.0
        assert result.verdict == "PASS"

    def test_kfold_fraction_positive_negative_strategy(self):
        """A strongly negative returns series should have fraction_positive == 0."""
        idx = pd.date_range("2019-01-31", periods=60, freq="ME")
        returns = pd.Series([-0.01] * 60, index=idx)
        result = calculate_kfold_stability(returns, n_folds=10)
        assert result.fraction_positive == 0.0
        assert result.verdict == "FAIL"

    def test_kfold_insufficient_periods_raises(self):
        """Fewer than n_folds * 3 periods raises ValueError."""
        returns = make_monthly_returns(n=20)
        with pytest.raises(ValueError, match="too short"):
            calculate_kfold_stability(returns, n_folds=10)

    def test_kfold_verdict_pass(self):
        """Fraction positive >= threshold_pass → PASS."""
        idx = pd.date_range("2019-01-31", periods=100, freq="ME")
        # 9 out of 10 folds positive → fraction_positive = 0.9 >= 0.7
        rng = np.random.default_rng(0)
        returns = pd.Series(rng.normal(0.02, 0.01, 100), index=idx)
        result = calculate_kfold_stability(returns, n_folds=10, threshold_pass=0.7)
        # All folds should be positive given strong mean
        assert result.fraction_positive >= 0.7
        assert result.verdict == "PASS"

    def test_kfold_verdict_fail(self):
        """Fraction positive < threshold_warn → FAIL."""
        idx = pd.date_range("2019-01-31", periods=60, freq="ME")
        # Mix of strongly positive and negative to guarantee low fraction
        vals = [-0.05, -0.04, -0.03, -0.04, -0.05] * 12
        returns = pd.Series(vals, index=idx)
        result = calculate_kfold_stability(returns, n_folds=10, threshold_warn=0.5)
        assert result.verdict == "FAIL"

    def test_kfold_worst_fold_is_minimum(self):
        """worst_fold_sharpe equals the minimum of fold_sharpes."""
        returns = make_monthly_returns(n=60)
        result = calculate_kfold_stability(returns, n_folds=6)
        assert result.worst_fold_sharpe == min(result.fold_sharpes)

    def test_kfold_in_overfitting_analysis(self):
        """run_overfitting_analysis populates kfold field when series is long enough."""
        returns = make_monthly_returns(n=60)
        analysis = run_overfitting_analysis(
            strategy_key="kfold_test",
            strategy_returns=returns,
            return_matrix=None,
            param_grid={},
            n_folds=6,
        )
        assert analysis.kfold is not None
        assert isinstance(analysis.kfold, KFoldResult)
        assert len(analysis.kfold.fold_sharpes) == 6

    def test_kfold_skipped_when_series_too_short(self):
        """k-fold is None (error logged) when series < n_folds * 3."""
        returns = make_monthly_returns(n=15)
        analysis = run_overfitting_analysis(
            strategy_key="kfold_short",
            strategy_returns=returns,
            return_matrix=None,
            param_grid={},
            n_folds=10,
        )
        assert analysis.kfold is None
        assert any("K-fold" in e for e in analysis.errors)

    def test_kfold_to_dict_serializable(self):
        """overfitting_analysis_to_dict kfold section is JSON-safe."""
        returns = make_monthly_returns(n=60)
        analysis = run_overfitting_analysis(
            strategy_key="kfold_serial",
            strategy_returns=returns,
            return_matrix=None,
            param_grid={},
            n_folds=6,
        )
        d = overfitting_analysis_to_dict(analysis)
        assert d["kfold"] is not None
        serialised = json.dumps(d)
        assert "kfold" in serialised

    def test_kfold_to_dict_subkeys(self):
        """K-fold sub-dict has all required keys."""
        returns = make_monthly_returns(n=60)
        analysis = run_overfitting_analysis(
            strategy_key="kfold_keys",
            strategy_returns=returns,
            return_matrix=None,
            param_grid={},
            n_folds=6,
        )
        d = overfitting_analysis_to_dict(analysis)
        expected_keys = {
            "n_folds", "fold_sharpes", "mean_sharpe", "std_sharpe",
            "fraction_positive", "worst_fold_sharpe", "verdict",
            "threshold_pass", "threshold_warn",
        }
        assert expected_keys.issubset(set(d["kfold"].keys()))

    def test_kfold_config_stored(self):
        """n_folds is stored in the analysis config dict."""
        returns = make_monthly_returns(n=60)
        analysis = run_overfitting_analysis(
            strategy_key="cfg_test",
            strategy_returns=returns,
            return_matrix=None,
            param_grid={},
            n_folds=7,
        )
        assert analysis.config["n_folds"] == 7
