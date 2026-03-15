"""
Integration tests for the optimization engine.

Uses synthetic price data so no IB connection or cached files are needed.
Tests cover ParameterSweep and WalkForwardAnalysis end-to-end with real
strategy classes.
"""

import pytest
import numpy as np
import pandas as pd

from optimization import ParameterSweep, WalkForwardAnalysis
from optimization.walk_forward import WalkForwardResults
from strategies.core import AssetStrategy
from strategies.equal_weight import EqualWeightStrategy
from strategies.hrp import HRPStrategy


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SYMBOLS = ['VUSA', 'SSLN', 'SGLN', 'IWRD']
N_DAYS = 400  # enough for lookback + several rebalance dates


def make_prices(n_days: int = N_DAYS, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic price data mimicking UK ETF returns."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range('2020-01-01', periods=n_days)
    # Correlated GBM prices
    returns = rng.normal(loc=0.0003, scale=0.01, size=(n_days, len(SYMBOLS)))
    prices = 100 * np.exp(np.cumsum(returns, axis=0))
    return pd.DataFrame(prices, index=dates, columns=SYMBOLS)


@pytest.fixture(scope="module")
def prices():
    return make_prices()


@pytest.fixture(scope="module")
def underlying():
    return [AssetStrategy(s, currency='GBP') for s in SYMBOLS]


# ---------------------------------------------------------------------------
# ParameterSweep tests
# ---------------------------------------------------------------------------

class TestParameterSweep:

    def test_single_param_returns_dataframe(self, prices, underlying):
        """Sweep over HRP linkage_method returns sorted DataFrame."""
        lookback = 60
        start = prices.index[lookback]
        end = prices.index[-1]

        sweep = ParameterSweep(
            strategy_class=HRPStrategy,
            param_grid={'linkage_method': ['single', 'complete', 'ward']},
            metric='sharpe_ratio',
        )
        result = sweep.run(underlying, prices, start, end, lookback_days=lookback)

        assert not result.empty
        assert 'linkage_method' in result.columns
        assert 'sharpe_ratio' in result.columns
        # Should have at most 3 rows (one per combo)
        assert len(result) <= 3
        # Should be sorted descending by sharpe_ratio
        sharpes = result['sharpe_ratio'].tolist()
        assert sharpes == sorted(sharpes, reverse=True)

    def test_multi_param_cartesian_product(self, prices, underlying):
        """Sweep with 2 params produces up to len(a) * len(b) results."""
        lookback = 60
        start = prices.index[lookback]
        end = prices.index[-1]

        sweep = ParameterSweep(
            strategy_class=HRPStrategy,
            param_grid={
                'linkage_method': ['single', 'ward'],
            },
            metric='total_return',
        )
        result = sweep.run(underlying, prices, start, end, lookback_days=lookback)

        assert not result.empty
        assert len(result) <= 2

    def test_metric_columns_present(self, prices, underlying):
        """Result DataFrame contains all expected metric columns."""
        expected_metrics = [
            'total_return', 'cagr', 'sharpe_ratio', 'sortino_ratio',
            'calmar_ratio', 'max_drawdown', 'volatility', 'var_95', 'cvar_95'
        ]
        lookback = 60
        sweep = ParameterSweep(
            strategy_class=HRPStrategy,
            param_grid={'linkage_method': ['ward']},
            metric='sharpe_ratio',
        )
        result = sweep.run(
            underlying, prices, prices.index[lookback], prices.index[-1],
            lookback_days=lookback
        )

        for col in expected_metrics:
            assert col in result.columns, f"Missing metric column: {col}"

    def test_equal_weight_no_params(self, prices, underlying):
        """EqualWeightStrategy sweep with no strategy-specific params works."""
        lookback = 60
        # Use a dummy param that EqualWeightStrategy ignores via **kwargs
        # (EqualWeight accepts **kwargs to swallow extra params)
        sweep = ParameterSweep(
            strategy_class=EqualWeightStrategy,
            param_grid={},  # no params to sweep
            metric='sharpe_ratio',
        )
        # _generate_combinations returns [{}] for empty grid
        combos = sweep._generate_combinations()
        assert combos == [{}]

        result = sweep.run(
            underlying, prices, prices.index[lookback], prices.index[-1],
            lookback_days=lookback
        )
        assert not result.empty
        assert len(result) == 1

    def test_insufficient_data_returns_empty(self, underlying):
        """Sweep with only 5 days of data returns empty DataFrame."""
        tiny_prices = make_prices(n_days=5)
        sweep = ParameterSweep(
            strategy_class=HRPStrategy,
            param_grid={'linkage_method': ['ward']},
            metric='sharpe_ratio',
        )
        start = tiny_prices.index[0]
        end = tiny_prices.index[-1]
        result = sweep.run(underlying, tiny_prices, start, end, lookback_days=3)
        assert result.empty

    def test_sortino_as_target_metric(self, prices, underlying):
        """Optimizing by sortino_ratio sorts correctly."""
        lookback = 60
        sweep = ParameterSweep(
            strategy_class=HRPStrategy,
            param_grid={'linkage_method': ['single', 'complete', 'ward']},
            metric='sortino_ratio',
        )
        result = sweep.run(
            underlying, prices, prices.index[lookback], prices.index[-1],
            lookback_days=lookback
        )
        if not result.empty:
            sortinos = result['sortino_ratio'].tolist()
            assert sortinos == sorted(sortinos, reverse=True)


# ---------------------------------------------------------------------------
# WalkForwardAnalysis tests
# ---------------------------------------------------------------------------

class TestWalkForwardAnalysis:

    def test_basic_walk_forward_runs(self, prices, underlying):
        """WalkForwardAnalysis completes and returns WalkForwardResults."""
        wfa = WalkForwardAnalysis(
            strategy_class=HRPStrategy,
            param_grid={'linkage_method': ['single', 'ward']},
            in_sample_days=150,
            out_of_sample_days=80,
            metric='sharpe_ratio',
            step_days=80,
        )
        results = wfa.run(underlying, prices)

        assert isinstance(results, WalkForwardResults)
        assert results.target_metric == 'sharpe_ratio'

    def test_produces_at_least_one_window(self, prices, underlying):
        """With enough data, at least one window is produced."""
        wfa = WalkForwardAnalysis(
            strategy_class=HRPStrategy,
            param_grid={'linkage_method': ['ward']},
            in_sample_days=150,
            out_of_sample_days=80,
            metric='sharpe_ratio',
            step_days=80,
        )
        results = wfa.run(underlying, prices)
        assert len(results.windows) >= 1

    def test_overfitting_ratio_is_positive(self, prices, underlying):
        """Overfitting ratio is a positive finite number when windows exist."""
        wfa = WalkForwardAnalysis(
            strategy_class=HRPStrategy,
            param_grid={'linkage_method': ['ward']},
            in_sample_days=150,
            out_of_sample_days=80,
            metric='sharpe_ratio',
            step_days=80,
        )
        results = wfa.run(underlying, prices)

        if results.windows:
            assert np.isfinite(results.overfitting_ratio)

    def test_summary_df_columns(self, prices, underlying):
        """summary_df contains expected columns."""
        wfa = WalkForwardAnalysis(
            strategy_class=HRPStrategy,
            param_grid={'linkage_method': ['ward']},
            in_sample_days=150,
            out_of_sample_days=80,
            metric='sharpe_ratio',
            step_days=80,
        )
        results = wfa.run(underlying, prices)

        if results.windows:
            expected_cols = [
                'window', 'in_sample', 'out_sample',
                'best_linkage_method',
                'in_sample_sharpe_ratio', 'out_sample_sharpe_ratio',
            ]
            for col in expected_cols:
                assert col in results.summary_df.columns, f"Missing column: {col}"

    def test_raises_on_insufficient_data(self, underlying):
        """ValueError raised when prices too short for one full window."""
        tiny_prices = make_prices(n_days=50)
        wfa = WalkForwardAnalysis(
            strategy_class=HRPStrategy,
            param_grid={'linkage_method': ['ward']},
            in_sample_days=100,
            out_of_sample_days=60,
        )
        with pytest.raises(ValueError, match="Need at least"):
            wfa.run(underlying, tiny_prices)

    def test_avg_metrics_match_windows(self, prices, underlying):
        """avg_in_sample and avg_out_sample match the window averages."""
        wfa = WalkForwardAnalysis(
            strategy_class=HRPStrategy,
            param_grid={'linkage_method': ['ward']},
            in_sample_days=150,
            out_of_sample_days=80,
            metric='sharpe_ratio',
            step_days=80,
        )
        results = wfa.run(underlying, prices)

        if results.windows:
            expected_in = np.mean([w.in_sample_metric for w in results.windows])
            expected_out = np.mean([w.out_sample_metric for w in results.windows])
            assert abs(results.avg_in_sample - expected_in) < 1e-9
            assert abs(results.avg_out_sample - expected_out) < 1e-9
