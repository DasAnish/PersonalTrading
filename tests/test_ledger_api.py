"""Tests for the ledger API blueprint (scripts/server/ledger.py) + scoped live-risk."""

import pytest

import analytics.ledger as ledger_mod
import scripts.server.ledger as server_ledger
import scripts.server.risk as risk_mod
from scripts.server.app import create_app

FAKE_POSITIONS = (
    [{"symbol": "VUSA", "shares": 10.0, "price": 100.0, "value": 1000.0}],
    True,
    "2026-01-05T00:00:00Z",
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger_mod, "LEDGER_PATH", tmp_path / "ledger.json")
    monkeypatch.setattr(server_ledger, "_load_positions", lambda: FAKE_POSITIONS)
    monkeypatch.setattr(risk_mod, "_load_positions", lambda: FAKE_POSITIONS)
    monkeypatch.setattr(server_ledger, "_definition_exists", lambda k: k == "hrp_ward")
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_empty_ledger_is_all_personal(client):
    d = client.get("/api/ledger").get_json()
    assert d["strategies"] == {}
    assert d["personal"]["holdings"] == {"VUSA": 10.0}
    assert d["personal"]["value"] == 1000.0
    assert d["events_count"] == 0


def test_mark_traded_creates_slice_and_reduces_personal(client):
    body = {
        "strategy": "hrp_ward",
        "trade_date": "2026-01-05",
        "external_cash_delta": 1000.0,
        "fills": [{"symbol": "VUSA", "shares_delta": 6.0, "price": 100.0}],
    }
    r = client.post("/api/ledger/mark-traded", json=body)
    assert r.status_code == 201
    assert r.get_json()["slice"]["holdings"] == {"VUSA": 6.0}

    d = client.get("/api/ledger").get_json()
    assert "hrp_ward" in d["strategies"]
    assert d["personal"]["holdings"] == {"VUSA": 4.0}  # 10 IB - 6 claimed
    assert d["events_count"] == 1


def test_mark_traded_unknown_strategy_400(client):
    r = client.post(
        "/api/ledger/mark-traded",
        json={
            "strategy": "nope",
            "trade_date": "2026-01-05",
            "external_cash_delta": 1.0,
        },
    )
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_mark_traded_bad_event_400(client):
    # valid strategy but no fills and no cash movement -> ledger validation 400
    r = client.post(
        "/api/ledger/mark-traded",
        json={"strategy": "hrp_ward", "trade_date": "2026-01-05"},
    )
    assert r.status_code == 400


def test_reconciliation_flags_overclaim(client):
    client.post(
        "/api/ledger/mark-traded",
        json={
            "strategy": "hrp_ward",
            "trade_date": "2026-01-05",
            "fills": [{"symbol": "VUSA", "shares_delta": 12.0, "price": 100.0}],
        },
    )
    d = client.get("/api/ledger").get_json()
    assert d["reconciliation"] == [
        {"symbol": "VUSA", "ledger_shares": 12.0, "ib_shares": 10.0}
    ]


def test_scope_strategy_filters_live_risk(client):
    client.post(
        "/api/ledger/mark-traded",
        json={
            "strategy": "hrp_ward",
            "trade_date": "2026-01-05",
            "fills": [{"symbol": "VUSA", "shares_delta": 6.0, "price": 100.0}],
        },
    )
    d = client.get("/api/live-risk?scope=strategy:hrp_ward").get_json()
    assert d["scope"] == "strategy:hrp_ward"
    assert {p["symbol"] for p in d["positions"]} == {"VUSA"}
    assert d["positions"][0]["shares"] == 6.0
