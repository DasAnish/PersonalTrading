"""Tests for the virtual per-strategy allocation ledger (analytics/ledger.py)."""

import pandas as pd
import pytest

from analytics import ledger as L


@pytest.fixture
def path(tmp_path):
    return tmp_path / "strategy_ledger.json"


def _buy(strategy, symbol, shares, price, commission=0.0, cash=0.0, date="2026-01-05"):
    return {
        "strategy": strategy,
        "trade_date": date,
        "external_cash_delta": cash,
        "fills": [
            {
                "symbol": symbol,
                "shares_delta": shares,
                "price": price,
                "commission": commission,
            }
        ],
    }


def test_empty_ledger_is_all_personal(path):
    led = L.load_ledger(path)
    assert led == {"schema_version": 1, "events": []}
    assert L.personal_holdings({"VUSA": 10.0}, led) == {"VUSA": 10.0}


def test_accumulate_and_sell(path):
    L.append_event(_buy("hrp_15vol", "VUSA", 8.0, 95.0), path)
    L.append_event(_buy("hrp_15vol", "VUSA", -3.0, 100.0), path)
    led = L.load_ledger(path)
    assert L.holdings_by_strategy(led) == {"hrp_15vol": {"VUSA": 5.0}}
    # Selling the whole position drops the near-zero holding entirely.
    L.append_event(_buy("hrp_15vol", "VUSA", -5.0, 101.0), path)
    assert L.holdings_by_strategy(L.load_ledger(path)) == {"hrp_15vol": {}}


def test_cash_math(path):
    # fund 1000, buy 8 @ 95.23 with 3.0 commission
    L.append_event(_buy("s", "VUSA", 8.0, 95.23, commission=3.0, cash=1000.0), path)
    cash = L.cash_by_strategy(L.load_ledger(path))["s"]
    assert cash == pytest.approx(1000.0 - 8 * 95.23 - 3.0)


def test_personal_is_ib_minus_claimed(path):
    L.append_event(_buy("s1", "VUSA", 6.0, 95.0), path)
    L.append_event(_buy("s2", "VUSA", 2.0, 96.0), path)
    led = L.load_ledger(path)
    # IB holds 10 VUSA; slices claim 8 -> personal residual 2 (floored at 0 elsewhere)
    assert L.personal_holdings({"VUSA": 10.0}, led) == {"VUSA": 2.0}
    assert L.personal_holdings({"VUSA": 8.0}, led) == {"VUSA": 0.0}


def test_reconcile_flags_overclaim(path):
    L.append_event(_buy("s", "VUSA", 10.0, 95.0), path)
    led = L.load_ledger(path)
    rows = L.reconcile({"VUSA": 8.0}, led)  # ledger claims 10, IB holds 8
    assert rows == [{"symbol": "VUSA", "ledger_shares": 10.0, "ib_shares": 8.0}]
    assert L.reconcile({"VUSA": 10.0}, led) == []  # exact match, no flag


def test_slice_nav_matches_hand_computed(path):
    # Buy 10 VUSA @ 100, fund 1000 -> slice cash = 1000 - 1000 = 0.
    L.append_event(_buy("s", "VUSA", 10.0, 100.0, cash=1000.0, date="2026-01-05"), path)
    closes = {
        "VUSA": pd.Series(
            [100.0, 110.0, 121.0],
            index=pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]),
        )
    }
    nav = L.slice_nav_series(L.load_ledger(path), "s", closes)
    # 10 shares * close + 0 cash
    assert nav.loc["2026-01-05"] == pytest.approx(1000.0)
    assert nav.loc["2026-01-06"] == pytest.approx(1100.0)
    assert nav.loc["2026-01-07"] == pytest.approx(1210.0)


def test_slice_value():
    assert (
        L.slice_value({"VUSA": 5.0, "SGLN": 2.0}, {"VUSA": 100.0, "SGLN": 50.0})
        == 600.0
    )


@pytest.mark.parametrize(
    "bad",
    [
        {"strategy": "", "trade_date": "2026-01-05", "external_cash_delta": 1.0},
        {"strategy": "s", "trade_date": "not-a-date", "external_cash_delta": 1.0},
        {
            "strategy": "s",
            "trade_date": "2026-01-05",
            "fills": [],
            "external_cash_delta": 0.0,
        },
        {
            "strategy": "s",
            "trade_date": "2026-01-05",
            "fills": [{"symbol": "VUSA", "shares_delta": 1.0, "price": 0.0}],
        },
    ],
)
def test_bad_events_rejected(path, bad):
    with pytest.raises(ValueError):
        L.append_event(bad, path)


def test_round_trip_stable(path):
    e = L.append_event(_buy("s", "VUSA", 8.0, 95.0, cash=1000.0), path)
    assert "id" in e and "recorded_at" in e
    led = L.load_ledger(path)
    assert led["events"][0]["id"] == e["id"]
    assert led["schema_version"] == L.LEDGER_SCHEMA_VERSION
