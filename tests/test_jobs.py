"""
Tests for scripts/server/jobs.py — the REST job runner.

Covers the request-validation surface (bad keys, bad steps, missing
definitions), the happy path with a stubbed step command, and the new
persistence layer: job.json mirrored per job dir, reloaded on boot, with
in-flight jobs from a dead process marked ``interrupted``.
"""

import json
import sys
import time

import pytest

from scripts.server import jobs as jobs_module
from scripts.server.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Test client with jobs state isolated to tmp_path."""
    defs_dir = tmp_path / "strategy_definitions"
    (defs_dir / "allocations").mkdir(parents=True)
    (defs_dir / "allocations" / "demo_strategy.json").write_text(
        json.dumps({"class": "demo"})
    )

    monkeypatch.setattr(jobs_module, "JOBS_DIR", tmp_path / "results" / "jobs")
    monkeypatch.setattr(jobs_module, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(jobs_module, "STRATEGY_DEFS_DIR", defs_dir)

    app = create_app()
    app.config.update(TESTING=True)
    with jobs_module._jobs_lock:
        jobs_module._jobs.clear()
    return app.test_client()


def _stub_step(monkeypatch, exit_code: int = 0):
    """Replace real pipeline subprocesses with an instant python -c."""

    def fake_command(step, strategy_key):
        return [sys.executable, "-c", f"print('{step} ok'); exit({exit_code})"]

    monkeypatch.setattr(jobs_module, "_step_command", fake_command)


def _wait_for(client, job_id: str, timeout_s: float = 30.0) -> dict:
    """Poll the status endpoint until the job leaves queued/running."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        payload = client.get(f"/api/run/status/{job_id}").get_json()
        if payload["state"] not in ("queued", "running"):
            return payload
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} did not finish within {timeout_s}s")


def test_rejects_invalid_strategy_key(client):
    assert client.post("/api/run/..%2Fetc").status_code in (400, 404)
    assert client.post("/api/run/no_such_strategy").status_code == 404


def test_rejects_bad_steps(client):
    resp = client.post("/api/run/demo_strategy", json={"steps": ["explode"]})
    assert resp.status_code == 400
    resp = client.post("/api/run/demo_strategy", json={"steps": []})
    assert resp.status_code == 400


def test_job_runs_and_persists(client, monkeypatch):
    _stub_step(monkeypatch, exit_code=0)
    resp = client.post("/api/run/demo_strategy", json={"steps": ["backtest"]})
    assert resp.status_code == 202
    job_id = resp.get_json()["job_id"]

    payload = _wait_for(client, job_id)
    assert payload["state"] == "done"
    assert payload["step_results"]["backtest"]["exit_code"] == 0

    persisted_path = jobs_module.JOBS_DIR / job_id / "job.json"
    assert persisted_path.exists()
    persisted = json.loads(persisted_path.read_text(encoding="utf-8"))
    assert persisted["state"] == "done"
    assert persisted["strategy_key"] == "demo_strategy"


def test_failed_step_marks_job_failed(client, monkeypatch):
    _stub_step(monkeypatch, exit_code=3)
    resp = client.post("/api/run/demo_strategy", json={"steps": ["backtest"]})
    job_id = resp.get_json()["job_id"]

    payload = _wait_for(client, job_id)
    assert payload["state"] == "failed"
    assert payload["error"]["step"] == "backtest"

    persisted_path = jobs_module.JOBS_DIR / job_id / "job.json"
    persisted = json.loads(persisted_path.read_text(encoding="utf-8"))
    assert persisted["state"] == "failed"


def test_load_persisted_jobs_marks_interrupted(client):
    # Simulate a job that was mid-flight when the previous process died.
    job_dir = jobs_module.JOBS_DIR / "deadbeef0001"
    job_dir.mkdir(parents=True)
    (job_dir / "job.json").write_text(
        json.dumps(
            {
                "job_id": "deadbeef0001",
                "strategy_key": "demo_strategy",
                "steps": ["backtest"],
                "state": "running",
                "current_step": "backtest",
                "step_results": {},
                "created_at": "2026-07-09T00:00:00",
            }
        )
    )

    loaded = jobs_module.load_persisted_jobs()
    assert loaded >= 1

    payload = client.get("/api/run/status/deadbeef0001").get_json()
    assert payload["state"] == "interrupted"
    # The interruption is persisted back too, so the next boot agrees.
    persisted = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    assert persisted["state"] == "interrupted"


def test_jobs_listing_includes_persisted(client):
    job_dir = jobs_module.JOBS_DIR / "deadbeef0002"
    job_dir.mkdir(parents=True)
    (job_dir / "job.json").write_text(
        json.dumps(
            {
                "job_id": "deadbeef0002",
                "strategy_key": "demo_strategy",
                "steps": ["backtest"],
                "state": "done",
                "current_step": None,
                "step_results": {"backtest": {"exit_code": 0}},
                "created_at": "2026-07-09T00:00:00",
            }
        )
    )
    jobs_module.load_persisted_jobs()

    listing = client.get("/api/run/jobs").get_json()
    assert any(j["job_id"] == "deadbeef0002" for j in listing)
