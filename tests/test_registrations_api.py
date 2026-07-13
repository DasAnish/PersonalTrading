"""Tests for the registration API blueprint (scripts/server/registrations.py)."""

import json

import pytest

import analytics.registrations as reg_mod
import scripts.server.registrations as server_reg
from scripts.server.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(reg_mod, "REGISTRATIONS_DIR", tmp_path / "registrations")
    monkeypatch.setattr(
        server_reg, "STATUS_PATH", tmp_path / "registration_status.json"
    )
    monkeypatch.setattr(server_reg, "_definition_exists", lambda k: k == "hrp_ward")
    monkeypatch.setattr(
        server_reg,
        "_metrics_for",
        lambda k: {
            "sharpe_ratio": 1.3,
            "max_drawdown": -0.18,
            "cagr": 0.11,
            "metrics_version": 2,
            "data_end": "2026-07-10",
        },
    )
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_register_prefills_from_metrics(client):
    r = client.post("/api/registrations", json={"strategy": "hrp_ward"})
    assert r.status_code == 201
    body = r.get_json()
    assert body["backtest"]["sharpe"] == 1.3
    assert body["backtest"]["max_drawdown"] == -0.18
    assert body["kill_criteria"]["portfolio_dd_limit"] == 0.30


def test_register_unknown_strategy_400(client):
    r = client.post("/api/registrations", json={"strategy": "nope"})
    assert r.status_code == 400


def test_list_merges_status(client, tmp_path):
    client.post("/api/registrations", json={"strategy": "hrp_ward"})
    (tmp_path / "registration_status.json").write_text(
        json.dumps({"hrp_ward": {"status": "breach", "reasons": ["x"]}})
    )
    listed = client.get("/api/registrations").get_json()
    assert listed[0]["strategy"] == "hrp_ward"
    assert listed[0]["status"]["status"] == "breach"


def test_delete_registration(client):
    client.post("/api/registrations", json={"strategy": "hrp_ward"})
    assert client.delete("/api/registrations/hrp_ward").status_code == 200
    assert client.delete("/api/registrations/hrp_ward").status_code == 404
