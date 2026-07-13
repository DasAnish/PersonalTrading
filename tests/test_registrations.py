"""Tests for pre-registration + kill-criteria evaluation (analytics/registrations.py)."""

from datetime import date

import pandas as pd
import pytest

import analytics.registrations as R


@pytest.fixture
def reg_dir(tmp_path):
    return tmp_path / "registrations"


def _bt(max_dd=-0.20, sharpe=1.2, cagr=0.10):
    return {
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "cagr": cagr,
        "metrics_version": 2,
        "data_end": "2026-07-10",
    }


def test_register_round_trip(reg_dir):
    entry = R.register("hrp_ward", _bt(), path_dir=reg_dir)
    assert entry["strategy"] == "hrp_ward"
    assert entry["kill_criteria"] == R.DEFAULT_KILL_CRITERIA
    loaded = R.load_registration("hrp_ward", path_dir=reg_dir)
    assert loaded["backtest"]["max_drawdown"] == -0.20
    assert [r["strategy"] for r in R.load_all_registrations(reg_dir)] == ["hrp_ward"]
    assert R.remove_registration("hrp_ward", path_dir=reg_dir) is True
    assert R.load_all_registrations(reg_dir) == []


def test_backtest_block_from_metrics():
    block = R.backtest_block_from_metrics(
        {
            "sharpe_ratio": 1.5,
            "max_drawdown": -0.1,
            "cagr": 0.2,
            "metrics_version": 2,
            "data_end": "2026-07-10",
        }
    )
    assert block["sharpe"] == 1.5 and block["max_drawdown"] == -0.1


def test_max_drawdown():
    s = pd.Series([100.0, 120.0, 60.0, 90.0])  # peak 120 -> trough 60 = -50%
    assert R.max_drawdown(s) == pytest.approx(-0.5)
    assert R.max_drawdown(pd.Series([100.0])) == 0.0


def test_evaluate_ok_within_envelope():
    registration = {
        "strategy": "s",
        "backtest": _bt(max_dd=-0.20),
        "kill_criteria": R.DEFAULT_KILL_CRITERIA,
        "review_date": None,
    }
    # slice DD -10% is within 1.5 x 20% = 30% envelope; portfolio DD -5% < 30%.
    slice_nav = pd.Series([100.0, 90.0])
    port = pd.Series([1000.0, 950.0])
    out = R.evaluate(registration, slice_nav, port, today=date(2026, 7, 13))
    assert out["status"] == "ok"
    assert out["envelope_dd"] == pytest.approx(-0.30)


def test_evaluate_breach_slice_envelope():
    registration = {
        "strategy": "s",
        "backtest": _bt(max_dd=-0.20),
        "kill_criteria": {"realized_dd_multiple": 1.5, "portfolio_dd_limit": 0.30},
    }
    # slice DD -40% exceeds -30% envelope -> breach.
    slice_nav = pd.Series([100.0, 60.0])
    out = R.evaluate(registration, slice_nav, pd.Series([1000.0, 990.0]))
    assert out["status"] == "breach"
    assert out["reasons"]


def test_evaluate_breach_portfolio_limit():
    registration = {
        "strategy": "s",
        "backtest": _bt(max_dd=-0.05),
        "kill_criteria": R.DEFAULT_KILL_CRITERIA,
    }
    # portfolio DD -35% exceeds absolute 30% limit -> breach.
    out = R.evaluate(registration, pd.Series([100.0, 99.0]), pd.Series([1000.0, 650.0]))
    assert out["status"] == "breach"


def test_evaluate_review_due():
    registration = {
        "strategy": "s",
        "backtest": _bt(max_dd=-0.20),
        "kill_criteria": R.DEFAULT_KILL_CRITERIA,
        "review_date": "2026-01-01",
    }
    out = R.evaluate(
        registration,
        pd.Series([100.0, 98.0]),
        pd.Series([1000.0, 990.0]),
        today=date(2026, 7, 13),
    )
    assert out["status"] == "review_due"


def test_evaluate_all_maps_by_strategy():
    regs = [
        {
            "strategy": "a",
            "backtest": _bt(-0.2),
            "kill_criteria": R.DEFAULT_KILL_CRITERIA,
        },
        {
            "strategy": "b",
            "backtest": _bt(-0.1),
            "kill_criteria": R.DEFAULT_KILL_CRITERIA,
        },
    ]
    navs = {"a": pd.Series([100.0, 95.0]), "b": pd.Series([100.0, 50.0])}
    out = R.evaluate_all(regs, navs, pd.Series([1000.0, 990.0]))
    assert out["a"]["status"] == "ok"
    assert out["b"]["status"] == "breach"  # -50% vs 1.5x10%=15% envelope
