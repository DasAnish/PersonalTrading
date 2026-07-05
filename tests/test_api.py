"""
Tests for scripts/server/api.py and scripts/server/data.py hardening:
- /api/compare rejects more than MAX_COMPARE_STRATEGIES strategy keys (400)
- Strategy keys containing path-traversal characters are rejected (400/404),
  never reaching the filesystem outside RESULTS_DIR
"""

import json

import pytest

from scripts.server.app import create_app
from scripts.server import data as data_module
from scripts.server.data import is_valid_strategy_key


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Flask test client backed by an isolated, monkeypatched RESULTS_DIR."""
    monkeypatch.setattr(data_module, "RESULTS_DIR", tmp_path)
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def _write_strategy(tmp_path, key: str, values):
    """Create a minimal on-disk strategy result directory."""
    strat_dir = tmp_path / "strategies" / key
    strat_dir.mkdir(parents=True, exist_ok=True)
    portfolio_history = [
        {"date": f"2020-01-{i + 1:02d}T00:00:00", "total_value": v}
        for i, v in enumerate(values)
    ]
    (strat_dir / "portfolio_history.json").write_text(json.dumps(portfolio_history))
    (strat_dir / "transactions.json").write_text("[]")
    (strat_dir / "weights_history.json").write_text("[]")
    (strat_dir / "metrics.json").write_text("{}")
    (strat_dir / "info.json").write_text("{}")


def _write_validation(tmp_path, key: str):
    """Create a validation.json fixture for a strategy."""
    strat_dir = tmp_path / "strategies" / key
    strat_dir.mkdir(parents=True, exist_ok=True)
    validation_data = {
        "strategy_key": key,
        "generated": "2026-01-01",
        "tests": [
            {
                "name": "dsr",
                "verdict": "PASS",
                "values": {"dsr": 0.85, "observed_sharpe": 0.92},
                "note": "",
            },
            {
                "name": "minbtl",
                "verdict": "PASS",
                "values": {"min_years": 1.5, "actual_years": 5.0},
                "note": "",
            },
            {
                "name": "cpcv",
                "verdict": "PASS",
                "values": {"prob_oos_sharpe_positive": 0.95},
                "note": "",
            },
            {
                "name": "bootstrap",
                "verdict": "PASS",
                "values": {"sharpe_mean": 0.78},
                "note": "fast mode",
            },
        ],
        "overall": "PASS",
    }
    (strat_dir / "validation.json").write_text(json.dumps(validation_data))


class TestIsValidStrategyKey:
    def test_accepts_simple_keys(self):
        assert is_valid_strategy_key("hrp_ward")
        assert is_valid_strategy_key("momentum-top2")
        assert is_valid_strategy_key("Strategy123")

    def test_rejects_traversal_and_slashes(self):
        assert not is_valid_strategy_key("..")
        assert not is_valid_strategy_key("../etc/passwd")
        assert not is_valid_strategy_key("foo/bar")
        assert not is_valid_strategy_key("")
        assert not is_valid_strategy_key(None)


class TestCompareEndpoint:
    def test_rejects_more_than_ten_strategies(self, client):
        keys = ",".join(f"strat{i}" for i in range(11))
        resp = client.get(f"/api/compare?strategies={keys}")
        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_accepts_ten_strategies_key_count_but_missing_data_404s(self, client):
        """Exactly 10 keys passes the count check (data absence is a separate 404)."""
        keys = ",".join(f"strat{i}" for i in range(10))
        resp = client.get(f"/api/compare?strategies={keys}")
        # Not rejected for count; fails later because the strategies don't exist
        assert resp.status_code == 404

    def test_rejects_traversal_key_in_query_string(self, client):
        resp = client.get("/api/compare?strategies=../../etc/passwd,valid_key")
        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_valid_comparison_succeeds(self, client, tmp_path):
        _write_strategy(tmp_path, "stratA", [100, 101, 102, 103, 104])
        _write_strategy(tmp_path, "stratB", [100, 99, 101, 102, 103])
        resp = client.get("/api/compare?strategies=stratA,stratB")
        assert resp.status_code == 200
        body = resp.get_json()
        assert set(body["strategies"]) == {"stratA", "stratB"}


class TestStrategyKeyPathTraversal:
    def test_strategy_endpoint_rejects_dotdot_key(self, client):
        resp = client.get("/api/strategy/..")
        assert resp.status_code in (400, 404)

    def test_overfitting_endpoint_rejects_dotdot_key(self, client):
        resp = client.get("/api/strategy/../overfitting")
        assert resp.status_code in (400, 404)
        body = resp.get_json()
        assert "error" in body

    def test_stress_test_endpoint_rejects_dotdot_key(self, client):
        resp = client.get("/api/strategy/../stress_test")
        assert resp.status_code in (400, 404)

    def test_valid_key_not_found_still_404s_normally(self, client):
        resp = client.get("/api/strategy/nonexistent_strategy")
        assert resp.status_code == 404


class TestValidationPayload:
    def test_validation_json_included_when_present(self, client, tmp_path):
        """When validation.json exists, it should be included in the strategy payload."""
        _write_strategy(tmp_path, "test_strat", [100, 101, 102])
        _write_validation(tmp_path, "test_strat")
        resp = client.get("/api/strategy/test_strat")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "validation" in body
        assert body["validation"]["overall"] == "PASS"
        assert len(body["validation"]["tests"]) == 4
        assert body["validation"]["tests"][0]["name"] == "dsr"

    def test_validation_omitted_when_absent(self, client, tmp_path):
        """When validation.json does not exist, the key should be omitted from payload."""
        _write_strategy(tmp_path, "test_strat2", [100, 101, 102])
        resp = client.get("/api/strategy/test_strat2")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "validation" not in body
