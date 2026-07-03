"""
Tests for analytics/stress_testing.py.

Covers: crisis window slicing, metric computation, leave-one-crisis-out,
and edge cases (no data in window, insufficient remaining data).
"""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from analytics.stress_testing import (
    CRISIS_PERIODS,
    CrisisPeriod,
    StressTester,
    StressTestReport,
    run_stress_test,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_values(start: str, end: str, seed: int = 42) -> pd.Series:
    """
    Generate a synthetic daily portfolio value series with a DatetimeIndex.
    Starts at 10_000 and follows a random walk with slight positive drift.
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, end, freq="B")  # business days
    n = len(dates)
    daily_returns = rng.normal(0.0003, 0.01, size=n)
    values = 10_000 * np.cumprod(1 + daily_returns)
    return pd.Series(values, index=dates)


@pytest.fixture
def long_series() -> pd.Series:
    """15-year series covering all five crisis periods."""
    return _make_values("2005-01-01", "2024-12-31")


@pytest.fixture
def short_series() -> pd.Series:
    """Series that covers only the 2020 COVID window."""
    return _make_values("2020-01-01", "2021-12-31")


@pytest.fixture
def single_crisis() -> CrisisPeriod:
    return CrisisPeriod(
        name="Test Crisis",
        start=date(2010, 1, 1),
        end=date(2010, 6, 30),
        description="Synthetic test crisis",
    )


# ---------------------------------------------------------------------------
# CRISIS_PERIODS constants
# ---------------------------------------------------------------------------


def test_crisis_periods_count():
    assert len(CRISIS_PERIODS) == 5


def test_crisis_periods_names():
    names = {c.name for c in CRISIS_PERIODS}
    assert "2008 GFC" in names
    assert "2020 COVID" in names
    assert "2022 Rate Spike" in names


def test_crisis_periods_ordering():
    """Crisis periods should be ordered chronologically."""
    for a, b in zip(CRISIS_PERIODS, CRISIS_PERIODS[1:]):
        assert a.start < b.start


def test_crisis_periods_non_overlapping():
    """No two crisis periods should overlap."""
    for a, b in zip(CRISIS_PERIODS, CRISIS_PERIODS[1:]):
        assert a.end < b.start


# ---------------------------------------------------------------------------
# StressTester — constructor
# ---------------------------------------------------------------------------


def test_requires_datetime_index():
    values = pd.Series([100, 101, 102])  # integer index
    with pytest.raises(ValueError, match="DatetimeIndex"):
        StressTester(values, "test")


def test_accepts_valid_series(long_series):
    tester = StressTester(long_series, "Test Strategy")
    assert tester.strategy_name == "Test Strategy"


# ---------------------------------------------------------------------------
# StressTester — crisis window slicing
# ---------------------------------------------------------------------------


def test_slice_returns_subset(long_series, single_crisis):
    tester = StressTester(long_series, "test", crises=[single_crisis])
    sliced = tester._slice(single_crisis)
    assert sliced is not None
    assert sliced.index[0] >= pd.Timestamp(single_crisis.start)
    assert sliced.index[-1] <= pd.Timestamp(single_crisis.end)


def test_slice_returns_none_when_no_overlap(short_series, single_crisis):
    """short_series is 2020-2021; single_crisis is 2010 — no overlap."""
    tester = StressTester(short_series, "test", crises=[single_crisis])
    sliced = tester._slice(single_crisis)
    assert sliced is None


# ---------------------------------------------------------------------------
# StressTester — crisis metrics
# ---------------------------------------------------------------------------


def test_crisis_metrics_has_data(long_series):
    covid = next(c for c in CRISIS_PERIODS if c.name == "2020 COVID")
    tester = StressTester(long_series, "test", crises=[covid])
    metrics = tester._analyse_crisis(covid)
    assert metrics.has_data is True


def test_crisis_metrics_no_data(short_series, single_crisis):
    """Series with no data in the crisis window should return has_data=False."""
    tester = StressTester(short_series, "test", crises=[single_crisis])
    metrics = tester._analyse_crisis(single_crisis)
    assert metrics.has_data is False
    assert metrics.sharpe == 0.0
    assert metrics.max_drawdown == 0.0


def test_crisis_metrics_return_sign(long_series):
    """Each metric is numerically meaningful."""
    covid = next(c for c in CRISIS_PERIODS if c.name == "2020 COVID")
    tester = StressTester(long_series, "test", crises=[covid])
    m = tester._analyse_crisis(covid)
    assert isinstance(m.total_return, float)
    assert isinstance(m.max_drawdown, float)
    assert m.max_drawdown <= 0.0  # drawdown is always non-positive


def test_crisis_metrics_recovery_days_type(long_series):
    covid = next(c for c in CRISIS_PERIODS if c.name == "2020 COVID")
    tester = StressTester(long_series, "test", crises=[covid])
    m = tester._analyse_crisis(covid)
    assert isinstance(m.recovery_days, int)


# ---------------------------------------------------------------------------
# StressTester — leave-one-crisis-out
# ---------------------------------------------------------------------------


def test_leave_one_out_count(long_series):
    """Should return one result per crisis that has enough data after exclusion."""
    tester = StressTester(long_series, "test")
    results = tester._run_leave_one_out()
    assert len(results) <= len(CRISIS_PERIODS)
    assert len(results) > 0


def test_leave_one_out_delta_type(long_series):
    tester = StressTester(long_series, "test")
    for r in tester._run_leave_one_out():
        assert isinstance(r.sharpe_delta, float)
        assert r.full_sharpe == pytest.approx(r.loo_sharpe + r.sharpe_delta, abs=1e-9)


def test_exclude_removes_correct_window(long_series, single_crisis):
    tester = StressTester(long_series, "test", crises=[single_crisis])
    excluded = tester._exclude(single_crisis)
    assert excluded is not None
    start_ts = pd.Timestamp(single_crisis.start)
    end_ts = pd.Timestamp(single_crisis.end)
    in_window = excluded[(excluded.index >= start_ts) & (excluded.index <= end_ts)]
    assert len(in_window) == 0


# ---------------------------------------------------------------------------
# StressTester — full run
# ---------------------------------------------------------------------------


def test_run_returns_report(long_series):
    report = StressTester(long_series, "My Strategy").run()
    assert isinstance(report, StressTestReport)
    assert report.strategy_name == "My Strategy"
    assert len(report.crisis_metrics) == len(CRISIS_PERIODS)


def test_run_to_dict_structure(long_series):
    report = run_stress_test(long_series, "Test")
    d = report.to_dict()
    assert "strategy_name" in d
    assert "crisis_metrics" in d
    assert "scenario_removal" in d
    assert isinstance(d["crisis_metrics"], list)
    assert isinstance(d["scenario_removal"], list)


def test_run_to_dict_crisis_fields(long_series):
    report = run_stress_test(long_series, "Test")
    for cm in report.to_dict()["crisis_metrics"]:
        assert "crisis_name" in cm
        assert "total_return_pct" in cm
        assert "max_drawdown_pct" in cm
        assert "sharpe" in cm
        assert "has_data" in cm


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------


def test_run_stress_test_convenience(long_series):
    report = run_stress_test(long_series, "HRP")
    assert isinstance(report, StressTestReport)
    assert report.strategy_name == "HRP"


def test_custom_crises(long_series, single_crisis):
    report = run_stress_test(long_series, "test", crises=[single_crisis])
    assert len(report.crisis_metrics) == 1
    assert report.crisis_metrics[0].crisis.name == "Test Crisis"


# ---------------------------------------------------------------------------
# Phase 7: public run_leave_one_out, Calmar deltas, rerun mode
# ---------------------------------------------------------------------------


def _engineered_dip_series(crisis: CrisisPeriod) -> pd.Series:
    """Flat value series with a sharp dip inside the crisis window."""
    dates = pd.date_range("2019-01-01", "2021-12-31", freq="B")
    values = pd.Series(100.0, index=dates)
    mask = (dates >= pd.Timestamp(crisis.start)) & (dates <= pd.Timestamp(crisis.end))
    values[mask] = 70.0
    return values


def test_scenario_result_has_calmar_fields():
    """New Calmar fields exist alongside the original Sharpe fields (renamed nothing)."""
    from analytics.stress_testing import ScenarioRemovalResult

    fields = set(ScenarioRemovalResult.__dataclass_fields__)
    assert {"full_sharpe", "loo_sharpe", "sharpe_delta"} <= fields  # originals intact
    assert {"full_calmar", "loo_calmar", "calmar_delta"} <= fields  # additions


def test_run_leave_one_out_excise_default(long_series):
    """Public API defaults to excise mode and returns one result per crisis."""
    tester = StressTester(long_series, "test")
    results = tester.run_leave_one_out()
    assert len(results) == len(CRISIS_PERIODS)
    for r in results:
        assert r.calmar_delta == pytest.approx(r.full_calmar - r.loo_calmar)
        assert r.sharpe_delta == pytest.approx(r.full_sharpe - r.loo_sharpe)


def test_alias_matches_public_excise(long_series):
    """The private _run_leave_one_out alias equals public excise output."""
    tester = StressTester(long_series, "test")
    alias = tester._run_leave_one_out()
    public = tester.run_leave_one_out(mode="excise")
    assert [r.crisis.name for r in alias] == [r.crisis.name for r in public]
    assert [r.sharpe_delta for r in alias] == [r.sharpe_delta for r in public]


def test_report_records_mode(long_series):
    """StressTestReport.to_dict carries the scenario_removal_mode and calmar keys."""
    report = StressTester(long_series, "test").run()
    d = report.to_dict()
    assert d["scenario_removal_mode"] == "excise"
    if d["scenario_removal"]:
        row = d["scenario_removal"][0]
        for key in ("full_calmar", "loo_calmar", "calmar_delta"):
            assert key in row


def test_excise_dip_removal_raises_sharpe():
    """Removing an engineered crisis dip should raise the Sharpe (positive delta)."""
    crisis = CRISIS_PERIODS[3]  # 2020 COVID
    values = _engineered_dip_series(crisis)
    tester = StressTester(values, "test", crises=[crisis])
    results = tester.run_leave_one_out(mode="excise")
    assert len(results) == 1
    # Excising the dip removes the large negative/positive shock returns; the
    # remaining flat series has a higher (less noisy) Sharpe -> positive delta.
    assert results[0].sharpe_delta > 0


def test_safe_round_maps_non_finite_to_none():
    """_safe_round keeps JSON valid by mapping inf/NaN to None."""
    import json
    from analytics.stress_testing import _safe_round

    assert _safe_round(float("inf"), 3) is None
    assert _safe_round(float("nan"), 3) is None
    assert _safe_round(1.23456, 3) == 1.235
    # And full to_dict output is JSON-serializable with no Infinity token.
    crisis = CRISIS_PERIODS[3]
    report = StressTester(_engineered_dip_series(crisis), "test", crises=[crisis]).run()
    s = json.dumps(report.to_dict())
    assert "Infinity" not in s and "NaN" not in s


def test_rerun_requires_inputs(long_series):
    """rerun mode without the required inputs raises a clear ValueError."""
    tester = StressTester(long_series, "test")
    with pytest.raises(ValueError, match="rerun"):
        tester.run_leave_one_out(mode="rerun")


def test_unknown_mode_raises(long_series):
    with pytest.raises(ValueError, match="[Uu]nknown"):
        tester = StressTester(long_series, "test")
        tester.run_leave_one_out(mode="bogus")


def test_insufficient_data_skips_crisis():
    """A crisis window covering most of the series is skipped, not crashed."""
    crisis = CrisisPeriod(
        name="Almost everything",
        start=date(2019, 1, 15),
        end=date(2021, 12, 15),
        description="covers nearly the whole series",
    )
    dates = pd.date_range("2019-01-01", "2021-12-31", freq="B")
    values = pd.Series(100.0, index=dates)
    tester = StressTester(values, "test", crises=[crisis])
    results = tester.run_leave_one_out(mode="excise")
    assert results == []  # skipped, no exception


@pytest.mark.slow
def test_rerun_vs_excise_wellformed():
    """Both modes run on real prices+strategy and produce well-formed results."""
    from strategies.strategy_loader import StrategyLoader
    from backtesting.engine import BacktestEngine
    from backtesting.runner import run_single_backtest
    from tests.test_backtest_e2e import make_simulated_prices

    prices = make_simulated_prices()
    strategy = StrategyLoader().build_strategy("equal_weight")
    engine = BacktestEngine(initial_capital=10_000, transaction_cost_bps=7.5)
    backtest_start = prices.index[252]
    backtest_end = prices.index[-1]

    full = run_single_backtest(strategy, prices, backtest_start, backtest_end, engine)
    values = full.portfolio_history["total_value"]
    tester = StressTester(values, strategy_name="equal_weight")

    excise = tester.run_leave_one_out(mode="excise")
    rerun = tester.run_leave_one_out(
        mode="rerun",
        strategy=strategy,
        prices=prices,
        engine=engine,
        backtest_start=backtest_start,
        backtest_end=backtest_end,
    )
    for results in (excise, rerun):
        for r in results:
            assert isinstance(r.full_sharpe, float)
            assert isinstance(r.calmar_delta, float)
