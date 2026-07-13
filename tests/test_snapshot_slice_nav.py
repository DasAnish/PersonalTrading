"""Tests for per-slice NAV snapshot logic (scripts/snapshot_nav.py W2.6)."""

import csv

import pytest

import analytics.ledger as ledger_mod
import scripts.snapshot_nav as sn

POSITIONS = [
    {"symbol": "VUSA", "shares": 10.0, "price": 120.0, "value": 1200.0},
    {"symbol": "VWRL", "shares": 4.0, "price": 50.0, "value": 200.0},
]


@pytest.fixture
def funded_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger_mod, "LEDGER_PATH", tmp_path / "ledger.json")
    monkeypatch.setattr(sn, "SLICE_NAV_CSV", tmp_path / "slice_nav_history.csv")
    monkeypatch.setattr(sn, "load_price_units", lambda: {})
    monkeypatch.setattr(sn, "close_price_base", lambda sym, units=None: 0.0)
    ledger_mod.append_event(
        {
            "strategy": "hrp_ward",
            "trade_date": "2026-01-05",
            "external_cash_delta": 1500.0,
            "fills": [{"symbol": "VUSA", "shares_delta": 6.0, "price": 100.0}],
        }
    )
    return tmp_path


def test_slice_rows_mark_at_live_prices(funded_ledger):
    rows, recon = sn.compute_slice_rows(POSITIONS, "2026-07-13")
    by = {r["strategy"]: r for r in rows}
    # Slice: 6 VUSA @120 = 720 holdings; cash 1500 - 6*100 = 900; slice 1620.
    assert by["hrp_ward"]["holdings_value"] == pytest.approx(720.0)
    assert by["hrp_ward"]["cash"] == pytest.approx(900.0)
    assert by["hrp_ward"]["slice_value"] == pytest.approx(1620.0)
    # Personal residual: 4 VUSA @120 (480) + 4 VWRL @50 (200) = 680.
    assert by["__personal__"]["holdings_value"] == pytest.approx(680.0)
    assert recon == []


def test_overclaim_is_reconciled(funded_ledger):
    ledger_mod.append_event(
        {
            "strategy": "hrp_ward",
            "trade_date": "2026-01-06",
            "fills": [{"symbol": "VUSA", "shares_delta": 10.0, "price": 100.0}],
        }
    )
    rows, recon = sn.compute_slice_rows(POSITIONS, "2026-07-13")
    assert recon == [{"symbol": "VUSA", "ledger_shares": 16.0, "ib_shares": 10.0}]


def test_upsert_replaces_same_day(funded_ledger):
    rows13, _ = sn.compute_slice_rows(POSITIONS, "2026-07-13")
    sn.upsert_slice_rows(rows13, "2026-07-13")
    sn.upsert_slice_rows(rows13, "2026-07-13")  # idempotent
    rows14, _ = sn.compute_slice_rows(POSITIONS, "2026-07-14")
    sn.upsert_slice_rows(rows14, "2026-07-14")

    with open(sn.SLICE_NAV_CSV, newline="", encoding="utf-8") as f:
        out = list(csv.DictReader(f))
    dates = {r["date"] for r in out}
    assert dates == {"2026-07-13", "2026-07-14"}
    # One day = 2 rows (hrp_ward + __personal__); two days = 4, not 6.
    assert len(out) == 4
