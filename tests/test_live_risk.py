"""Tests for scripts/server/risk.py — read-only live-risk endpoints."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from server.app import create_app  # noqa: E402
import server.risk as risk  # noqa: E402


@pytest.fixture
def client():
    return create_app().test_client()


def test_page_renders(client):
    assert client.get("/live-risk").status_code == 200


def test_api_fallback_shape(client, monkeypatch):
    """With no IB and no cache, the API returns a well-formed offline payload."""
    monkeypatch.setattr(risk, "_load_positions", lambda: ([], False, None))
    r = client.get("/api/live-risk")
    assert r.status_code == 200
    d = r.get_json()
    assert d["ib_online"] is False and d["banner"]
    assert d["positions"] == [] and d["hhi"] == 0.0
    assert {"var_95", "cvar_95", "drift", "correlation"} <= set(d)


def test_api_computes_metrics(client, monkeypatch):
    """With fixture positions + returns, VaR/CVaR/HHI/correlation populate."""
    positions = [
        {"symbol": "AAA", "shares": 10, "price": 100.0, "value": 1000.0},
        {"symbol": "BBB", "shares": 5, "price": 200.0, "value": 1000.0},
    ]
    monkeypatch.setattr(
        risk, "_load_positions", lambda: (positions, True, "2026-07-03T00:00:00")
    )
    idx = pd.date_range("2024-01-01", periods=300, freq="B")
    rng = __import__("numpy").random.default_rng(0)
    rets = pd.DataFrame(
        {"AAA": rng.normal(0.001, 0.02, 300), "BBB": rng.normal(0.001, 0.02, 300)},
        index=idx,
    )
    monkeypatch.setattr(risk, "_price_returns", lambda syms: rets[syms])

    d = client.get("/api/live-risk").get_json()
    assert d["ib_online"] is True
    assert d["var_95"] is not None and d["cvar_95"] is not None
    assert d["cvar_95"] <= d["var_95"]  # expected shortfall is worse than VaR
    assert abs(d["hhi"] - 0.5) < 1e-6  # two equal weights -> HHI 0.5
    assert "AAA" in d["correlation"]


def test_drift_flagging(client, monkeypatch):
    """Drift beyond ±5% vs target weights is flagged."""
    positions = [{"symbol": "AAA", "shares": 10, "price": 100.0, "value": 1000.0}]
    monkeypatch.setattr(risk, "_load_positions", lambda: (positions, True, "t"))
    monkeypatch.setattr(risk, "_price_returns", lambda syms: pd.DataFrame())
    # AAA is 100% held but target is 50% -> 50% drift, flagged.
    monkeypatch.setattr(risk, "_target_weights", lambda key: {"AAA": 0.5, "BBB": 0.5})

    d = client.get("/api/live-risk?strategy=whatever").get_json()
    by_sym = {row["symbol"]: row for row in d["drift"]}
    assert by_sym["AAA"]["flagged"] is True
    assert by_sym["BBB"]["flagged"] is True  # 0 held vs 50% target


def test_no_order_paths_in_source():
    src = Path("scripts/server/risk.py").read_text().lower()
    for forbidden in ("placeorder", "bracketorder", "submitorder", "cancelorder"):
        assert forbidden not in src
