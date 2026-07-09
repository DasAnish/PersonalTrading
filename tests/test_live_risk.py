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
    """With no IB, no cache, and no saved blend: well-formed empty payload.

    load_blend must be stubbed out — a preferred blend saved in the real
    results/ dir otherwise (correctly) drives a hypothetical target-weights
    payload with a non-zero HHI.
    """
    monkeypatch.setattr(risk, "_load_positions", lambda: ([], False, None))
    monkeypatch.setattr(risk, "load_blend", lambda: None)
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


def test_target_weights_fallback(client, monkeypatch):
    """No positions + a strategy key -> hypothetical risk from target weights."""
    monkeypatch.setattr(risk, "_load_positions", lambda: ([], False, None))
    monkeypatch.setattr(risk, "_target_weights", lambda key: {"AAA": 0.6, "BBB": 0.4})
    idx = pd.date_range("2024-01-01", periods=300, freq="B")
    rng = __import__("numpy").random.default_rng(1)
    rets = pd.DataFrame(
        {"AAA": rng.normal(0.001, 0.02, 300), "BBB": rng.normal(0.001, 0.02, 300)},
        index=idx,
    )
    monkeypatch.setattr(risk, "_price_returns", lambda syms: rets[syms])

    d = client.get("/api/live-risk?strategy=demo").get_json()
    assert d["source"] == "target_weights" and d["hypothetical"] is True
    assert d["weights"] == {"AAA": 0.6, "BBB": 0.4}
    assert d["var_95"] is not None and d["cvar_95"] is not None
    assert abs(d["hhi"] - (0.6**2 + 0.4**2)) < 1e-6
    # Drift is suppressed in hypothetical mode (current == target).
    assert d["drift"] == []


def test_source_none_when_no_data(client, monkeypatch):
    """No positions, no blend, no strategy target -> source 'none', metrics null."""
    monkeypatch.setattr(risk, "_load_positions", lambda: ([], False, None))
    monkeypatch.setattr(risk, "_target_weights", lambda key: {})
    monkeypatch.setattr(risk, "load_blend", lambda: {})
    d = client.get("/api/live-risk").get_json()
    assert d["source"] == "none" and d["hypothetical"] is False
    assert d["var_95"] is None and d["weights"] == {}


def test_enrich_excludes_ignored_and_backfills(monkeypatch):
    """IBKR is dropped; a zero-price position is valued from the close cache."""
    monkeypatch.setattr(risk, "load_price_units", lambda: {})
    monkeypatch.setattr(risk, "close_price_base", lambda sym, units: 50.0)
    raw = [
        {"symbol": "IBKR", "shares": 5, "price": 0.0, "value": 0.0},
        {"symbol": "VUSA", "shares": 10, "price": 0.0, "value": 0.0},
    ]
    out = risk._enrich_positions(raw)
    assert [p["symbol"] for p in out] == ["VUSA"]
    assert out[0]["price"] == 50.0 and out[0]["value"] == 500.0


def test_drift_defaults_to_blend(client, monkeypatch):
    """With no strategy key, drift target is the saved blend."""
    positions = [{"symbol": "AAA", "shares": 10, "price": 100.0, "value": 1000.0}]
    monkeypatch.setattr(risk, "_load_positions", lambda: (positions, True, "t"))
    monkeypatch.setattr(risk, "_price_returns", lambda syms: pd.DataFrame())
    monkeypatch.setattr(risk, "load_blend", lambda: {"demo": 1.0})
    monkeypatch.setattr(
        risk, "blended_target_weights", lambda blend: {"AAA": 0.5, "BBB": 0.5}
    )
    d = client.get("/api/live-risk").get_json()
    assert d["target_source"] == "blend"
    by_sym = {row["symbol"]: row for row in d["drift"]}
    assert by_sym["AAA"]["flagged"] is True  # 100% held vs 50% target


def test_blend_get_and_save(client, monkeypatch, tmp_path):
    """POST persists a blend; GET returns it with resolved target weights."""
    import analytics.blend as bm

    cfg = tmp_path / "preferred_blend.json"
    monkeypatch.setattr(risk, "load_blend", lambda: bm.load_blend(cfg))
    monkeypatch.setattr(risk, "save_blend", lambda b: bm.save_blend(b, path=cfg))
    monkeypatch.setattr(risk, "blended_target_weights", lambda blend: {"AAA": 1.0})

    r = client.post("/api/preferred-blend", json={"blend": {"s1": 0.4, "s2": 0.6}})
    assert r.status_code == 200
    assert r.get_json()["blend"] == {"s1": 0.4, "s2": 0.6}

    g = client.get("/api/preferred-blend").get_json()
    assert g["blend"] == {"s1": 0.4, "s2": 0.6}
    assert g["target_weights"] == {"AAA": 1.0}


def test_target_allocation(client, monkeypatch):
    """Blend × budget → per-asset amount and shares at cached close prices."""
    monkeypatch.setattr(risk, "load_blend", lambda: {"s1": 1.0})
    monkeypatch.setattr(
        risk, "blended_target_weights", lambda blend: {"AAA": 0.6, "BBB": 0.4}
    )
    monkeypatch.setattr(risk, "load_price_units", lambda: {})
    monkeypatch.setattr(
        risk, "close_price_base", lambda sym, units: {"AAA": 50.0, "BBB": 20.0}[sym]
    )
    d = client.get("/api/target-allocation?budget=10000").get_json()
    assert d["budget"] == 10000
    by = {r["symbol"]: r for r in d["target"]}
    assert by["AAA"]["amount"] == 6000.0 and by["AAA"]["shares"] == 120.0  # 6000/50
    assert by["BBB"]["amount"] == 4000.0 and by["BBB"]["shares"] == 200.0  # 4000/20


def test_target_allocation_no_price(client, monkeypatch):
    """A symbol with no cached/manual price yields shares=None, not a crash."""
    monkeypatch.setattr(risk, "load_blend", lambda: {"s1": 1.0})
    monkeypatch.setattr(risk, "blended_target_weights", lambda blend: {"LPLA": 1.0})
    monkeypatch.setattr(risk, "load_price_units", lambda: {})
    monkeypatch.setattr(risk, "close_price_base", lambda sym, units: None)
    d = client.get("/api/target-allocation?budget=5000").get_json()
    row = d["target"][0]
    assert row["amount"] == 5000.0 and row["price"] is None and row["shares"] is None


def test_blend_save_rejects_empty(client, monkeypatch, tmp_path):
    import analytics.blend as bm

    cfg = tmp_path / "b.json"
    monkeypatch.setattr(risk, "save_blend", lambda b: bm.save_blend(b, path=cfg))
    r = client.post("/api/preferred-blend", json={"blend": {}})
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_snapshot_writer_no_order_paths():
    """The IB snapshot writer must not contain any order-placement calls."""
    src = Path("scripts/snapshot_positions.py").read_text().lower()
    for forbidden in ("placeorder", "bracketorder", "submitorder", "cancelorder"):
        assert forbidden not in src


def test_no_order_paths_in_source():
    src = Path("scripts/server/risk.py").read_text().lower()
    for forbidden in ("placeorder", "bracketorder", "submitorder", "cancelorder"):
        assert forbidden not in src
