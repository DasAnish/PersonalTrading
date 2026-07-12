"""
Invariant tests for the 2026-07-10 audit findings — these exist so the
bug class can't quietly return:

  A1  metrics.json annualized monthly rebalance-period returns with
      sqrt(252), inflating Sharpe/volatility ~4.6x. Guarded by:
      annualization must be INFERRED from series spacing everywhere
      (analytics.metrics.summarize_performance is the single source).
  A2  mixed-vintage results (part of the library rebuilt against a
      truncated panel) were invisible. Guarded by: metrics carry
      data_end, rebuild_index emits a vintage block with mixed=True.
"""

import json

import numpy as np
import pandas as pd
import pytest

from analytics.metrics import (
    calculate_sharpe_ratio,
    calculate_volatility,
    infer_periods_per_year,
    summarize_performance,
)
from analytics.summary import generate_metrics_summary
from backtesting.results_io import serialize_backtest_results


def _series(freq: str, n: int, mu: float, sigma: float, seed: int = 7) -> pd.Series:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2018-01-31", periods=n, freq=freq)
    returns = rng.normal(mu, sigma, n)
    return pd.Series(100.0 * np.exp(np.cumsum(returns)), index=dates)


class TestInferPeriodsPerYear:
    def test_daily(self):
        s = _series("B", 300, 0.0003, 0.01)
        assert infer_periods_per_year(s.index) == 252

    def test_weekly(self):
        s = _series("W-FRI", 120, 0.001, 0.02)
        assert infer_periods_per_year(s.index) == 52

    def test_monthly(self):
        s = _series("ME", 60, 0.005, 0.03)
        assert infer_periods_per_year(s.index) == 12

    def test_quarterly(self):
        s = _series("QE", 24, 0.015, 0.05)
        assert infer_periods_per_year(s.index) == 4

    def test_too_short_defaults_to_daily(self):
        idx = pd.DatetimeIndex(["2024-01-01", "2024-02-01"])
        assert infer_periods_per_year(idx) == 252


class TestSummarizePerformance:
    def test_monthly_not_annualized_as_daily(self):
        """The A1 regression test: monthly series must use ppy=12."""
        values = _series("ME", 60, 0.008, 0.02)
        m = summarize_performance(values)
        assert m["periods_per_year"] == 12
        returns = values.pct_change().dropna()
        expected = calculate_sharpe_ratio(returns, periods_per_year=12)
        assert m["sharpe_ratio"] == pytest.approx(expected)
        # The daily-assumption number is ~4.6x larger; make sure we are
        # nowhere near it.
        inflated = calculate_sharpe_ratio(returns, periods_per_year=252)
        assert abs(m["sharpe_ratio"]) < abs(inflated) / 3

    def test_records_data_window(self):
        values = _series("ME", 24, 0.005, 0.02)
        m = summarize_performance(values)
        assert m["data_start"] == values.index[0].date().isoformat()
        assert m["data_end"] == values.index[-1].date().isoformat()

    def test_degenerate_series(self):
        m = summarize_performance(pd.Series(dtype=float))
        assert m["sharpe_ratio"] is None and m["data_end"] is None


class TestSerializeUsesCanonicalMetrics:
    def test_monthly_backtest_metrics_match_summarize(self):
        from backtesting.engine import BacktestResults

        values = _series("ME", 48, 0.006, 0.025)
        portfolio_history = pd.DataFrame(
            {"cash": 0.0, "total_value": values.values},
            index=pd.Index(values.index, name="timestamp"),
        )
        results = BacktestResults(
            strategy_name="synthetic",
            portfolio_history=portfolio_history,
            weights_history=None,
            transactions=[],
            final_value=float(values.iloc[-1]),
        )
        payload = serialize_backtest_results(results, "synthetic", {})
        expected = summarize_performance(values)
        assert payload["metrics"]["periods_per_year"] == 12
        assert payload["metrics"]["sharpe_ratio"] == pytest.approx(
            expected["sharpe_ratio"]
        )
        assert payload["metrics"]["data_end"] == expected["data_end"]


class TestGenerateMetricsSummaryInferred:
    def test_monthly_volatility_matches_summarize(self):
        """Verify generate_metrics_summary infers ppy and matches summarize_performance."""
        from backtesting.engine import BacktestResults

        # Create synthetic monthly portfolio history
        values = _series("ME", 48, 0.006, 0.025, seed=42)
        portfolio_history = pd.DataFrame(
            {"cash": 0.0, "total_value": values.values},
            index=pd.Index(values.index, name="timestamp"),
        )
        results = BacktestResults(
            strategy_name="synthetic",
            portfolio_history=portfolio_history,
            weights_history=None,
            transactions=[],
            final_value=float(values.iloc[-1]),
        )

        # Generate metrics using generate_metrics_summary
        generate_metrics_summary(results)
        metrics = results.metrics

        # Also get metrics from the canonical summarize_performance
        expected = summarize_performance(values)

        # Verify that periods_per_year is inferred correctly
        assert metrics["periods_per_year"] == 12
        assert expected["periods_per_year"] == 12

        # Verify volatility is within 5% (relative error)
        vol_metric = metrics["volatility"]
        vol_expected = expected["volatility"] * 100  # convert to percentage
        rel_error = abs(vol_metric - vol_expected) / abs(vol_expected)
        assert rel_error < 0.05, (
            f"Volatility mismatch: {vol_metric:.4f}% vs expected {vol_expected:.4f}%, "
            f"relative error {rel_error:.4f}"
        )

        # Verify Sharpe ratio is also consistent
        assert metrics["sharpe_ratio"] == pytest.approx(
            expected["sharpe_ratio"], rel=0.01
        )


class TestRebuildIndexVintage:
    def _write_strategy(self, results_dir, key, data_end):
        d = results_dir / "strategies" / key
        d.mkdir(parents=True)
        (d / "metrics.json").write_text(
            json.dumps({"sharpe_ratio": 1.0, "data_end": data_end})
        )
        (d / "info.json").write_text(json.dumps({"name": key}))

    def test_mixed_vintage_flagged(self, tmp_path):
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path("scripts").resolve()))
        from rebuild_index import rebuild

        self._write_strategy(tmp_path, "fresh", "2026-06-30")
        self._write_strategy(tmp_path, "stale", "2026-03-02")
        index = rebuild(tmp_path)
        assert index["vintage"]["mixed"] is True
        assert index["vintage"]["min_data_end"] == "2026-03-02"
        assert index["vintage"]["max_data_end"] == "2026-06-30"
        assert index["strategies"]["stale"]["data_end"] == "2026-03-02"

    def test_uniform_vintage_not_flagged(self, tmp_path):
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path("scripts").resolve()))
        from rebuild_index import rebuild

        self._write_strategy(tmp_path, "a", "2026-06-30")
        self._write_strategy(tmp_path, "b", "2026-06-30")
        index = rebuild(tmp_path)
        assert index["vintage"]["mixed"] is False
