"""Tests for the recommend-allocation state gatherer (scripts/recommend_allocation.py)."""

import json

import pytest

import analytics.ledger as ledger_mod
import scripts.recommend_allocation as RA


@pytest.fixture
def state(tmp_path, monkeypatch):
    results = tmp_path / "results"
    (results / "strategies" / "hrp_ward").mkdir(parents=True)
    # strategies_index with one strategy.
    (results / "strategies_index.json").write_text(
        json.dumps(
            {
                "strategies": {
                    "hrp_ward": {
                        "metrics": {
                            "sharpe_ratio": 1.4,
                            "cagr": 0.12,
                            "total_return": 0.5,
                            "max_drawdown": -0.15,
                            "data_end": "2026-07-10",
                        },
                    }
                }
            }
        )
    )
    (results / "strategies" / "hrp_ward" / "validation.json").write_text(
        json.dumps({"overall": "PASS"})
    )
    (results / "registration_status.json").write_text(
        json.dumps({"hrp_ward": {"status": "ok"}})
    )
    (results / "meta_portfolio.json").write_text(
        json.dumps(
            {
                "selected": ["hrp_ward"],
                "blend": {"hrp_ward": 1.0},
                "correlation_matrix": [[1.0]],
            }
        )
    )
    (results / "meta_selection.json").write_text(
        json.dumps(
            {"selection": {"total_return": 0.3}, "selection_percentile_vs_random": 80.0}
        )
    )
    # ledger with one slice.
    monkeypatch.setattr(ledger_mod, "LEDGER_PATH", tmp_path / "ledger.json")
    ledger_mod.append_event(
        {
            "strategy": "hrp_ward",
            "trade_date": "2026-01-05",
            "external_cash_delta": 1000.0,
            "fills": [{"symbol": "VUSA", "shares_delta": 5.0, "price": 100.0}],
        }
    )
    # Point the module at the tmp results tree + stub prices / IB.
    monkeypatch.setattr(RA, "RESULTS_DIR", results)
    monkeypatch.setattr(RA, "LIVE_POSITIONS", results / "live_positions.json")
    monkeypatch.setattr(RA, "NAV_CSV", tmp_path / "nav_history.csv")
    monkeypatch.setattr(RA, "load_price_units", lambda: {})
    monkeypatch.setattr(RA, "close_price_base", lambda s, units=None: 100.0)
    monkeypatch.setattr(RA, "_load_json", RA._load_json)  # keep real loader
    (tmp_path / "nav_history.csv").write_text(
        "date,net_liquidation,total_cash\n2026-07-12,5000,1500\n"
    )
    return results


def test_gather_assembles_all_blocks(state):
    payload = RA.gather(results_dir=state)
    assert payload["account_nav"]["net_liquidation"] == "5000"
    assert payload["constraints"]["max_portfolio_drawdown"] == 0.30
    # Strategy metrics + validation + registration merged.
    s = payload["strategies"]["hrp_ward"]
    assert (
        s["sharpe"] == 1.4 and s["validation"] == "PASS" and s["registration"] == "ok"
    )
    # Ledger slice present, cash = 1000 - 5*100 = 500, value = 500 held + 500 cash.
    slice_ = payload["ledger"]["strategies"]["hrp_ward"]
    assert slice_["cash"] == pytest.approx(500.0)
    assert slice_["slice_value"] == pytest.approx(1000.0)
    # Meta blocks present; correlation matrix stripped.
    assert payload["meta_portfolio"]["selected"] == ["hrp_ward"]
    assert "correlation_matrix" not in payload["meta_portfolio"]
    assert payload["meta_selection"]["selection_percentile_vs_random"] == 80.0


def test_gather_without_ib_positions(state):
    # No live_positions.json -> ib_positions_available False, personal empty.
    payload = RA.gather(results_dir=state)
    assert payload["ledger"]["ib_positions_available"] is False
    assert payload["ledger"]["personal"]["holdings"] == {}
