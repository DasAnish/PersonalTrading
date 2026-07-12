"""Background job runner: backtest/validate/overfitting via REST.

Lets an agent (or the user) trigger the full pipeline for one strategy with
a curl to the dashboard server and poll for the outcome:

    POST /api/run/<strategy_key>            -> {"job_id": ...}
    GET  /api/run/status/<job_id>           -> state, current step, result
    GET  /api/run/jobs                      -> recent jobs

Each step runs as a fresh ``python scripts/...`` subprocess, so code changes
on disk are always picked up (the long-lived waitress server never executes
strategy code itself). Steps, in order:

    backtest     python scripts/run_backtest.py --use-definitions --strategy K
    validate     python scripts/validate_strategy.py --strategy K --json
    overfitting  python scripts/run_overfitting.py --strategy K

On completion the status payload embeds metrics.json / validation.json /
overfitting_analysis.json from results/strategies/<key>/ so the caller gets
the verdict without a second round of requests.

NOTE: this runner never touches IB order endpoints — it only shells out to
the read-only research scripts above. No order placement, ever.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import uuid
from collections import OrderedDict
from datetime import datetime

from flask import Blueprint, jsonify, request

from .data import (
    BASE_DIR,
    RESULTS_DIR,
    STRATEGY_DEFS_DIR,
    is_valid_strategy_key,
)

logger = logging.getLogger(__name__)

jobs_bp = Blueprint("jobs", __name__)

JOBS_DIR = RESULTS_DIR / "jobs"

ALL_STEPS = ("backtest", "validate", "overfitting")

# Serialize heavy pipeline work: strategies share the results index and the
# machine; two concurrent --all-style runs would thrash. 2 slots matches the
# two builder agents.
MAX_CONCURRENT_JOBS = 2

LOG_TAIL_LINES = 25

_jobs: "OrderedDict[str, dict]" = OrderedDict()
_jobs_lock = threading.Lock()
_slots = threading.Semaphore(MAX_CONCURRENT_JOBS)

# Per-step subprocess timeout (seconds). Backtests are minutes; validation
# bootstrap can be slow. Generous but bounded so a hung child can't pin a
# job slot forever.
STEP_TIMEOUT_S = 45 * 60


def _persist_job(job: dict) -> None:
    """
    Mirror the job dict to results/jobs/<id>/job.json so history survives a
    server restart (job state used to be in-memory only). Best-effort: a
    persistence failure must never take a job down with it.
    """
    try:
        job_dir = JOBS_DIR / job["job_id"]
        job_dir.mkdir(parents=True, exist_ok=True)
        with open(job_dir / "job.json", "w", encoding="utf-8") as f:
            json.dump(job, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not persist job {job.get('job_id')}: {e}")


def load_persisted_jobs() -> int:
    """
    Reload job history from results/jobs/*/job.json into memory (newest 200,
    matching the in-memory bound). Jobs that were queued/running when the
    previous process died can never finish — mark them ``interrupted``.
    Called once from create_app(); returns the number of jobs loaded.
    """
    if not JOBS_DIR.is_dir():
        return 0
    loaded: list[dict] = []
    for path in JOBS_DIR.glob("*/job.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                job = json.load(f)
        except Exception as e:
            logger.warning(f"Skipping unreadable {path}: {e}")
            continue
        if not isinstance(job, dict) or "job_id" not in job:
            continue
        if job.get("state") in ("queued", "running"):
            job["state"] = "interrupted"
            job["current_step"] = None
            job["error"] = {"reason": "server restarted while job was active"}
            _persist_job(job)
        loaded.append(job)

    loaded.sort(key=lambda j: j.get("created_at") or "")
    with _jobs_lock:
        for job in loaded[-200:]:
            _jobs.setdefault(job["job_id"], job)
    if loaded:
        logger.info(f"Reloaded {min(len(loaded), 200)} persisted jobs")
    return min(len(loaded), 200)


def _definition_exists(strategy_key: str) -> bool:
    """A key is runnable if any strategy_definitions subdir has its file."""
    for sub in ("allocations", "composed", "overlays", "portfolios"):
        for ext in (".json", ".yaml"):
            if (STRATEGY_DEFS_DIR / sub / f"{strategy_key}{ext}").exists():
                return True
    return False


def _estimate_n_trials(strategy_key: str) -> int:
    """
    n_trials for run_overfitting.py Mode 2: count sibling definitions that
    share this key's ``class`` (the effective number of variants tried),
    floored at 2 — same idea as build_n_trials_map's class-sibling tier,
    kept dependency-free so the server doesn't import the analysis stack.
    """
    target_class = None
    definitions: list[tuple[str, str]] = []  # (key, class)
    for sub in ("allocations", "composed", "portfolios"):
        subdir = STRATEGY_DEFS_DIR / sub
        if not subdir.exists():
            continue
        for path in subdir.glob("*.json"):
            try:
                with open(path, "r") as f:
                    cls = json.load(f).get("class")
            except Exception:
                continue
            definitions.append((path.stem, cls))
            if path.stem == strategy_key:
                target_class = cls
    if target_class is None:
        return 2
    siblings = sum(1 for _, cls in definitions if cls == target_class)
    return max(2, siblings)


def _step_command(step: str, strategy_key: str) -> list[str]:
    if step == "backtest":
        return [
            sys.executable,
            "scripts/run_backtest.py",
            "--use-definitions",
            "--strategy",
            strategy_key,
        ]
    if step == "validate":
        return [
            sys.executable,
            "scripts/validate_strategy.py",
            "--strategy",
            strategy_key,
            "--json",
        ]
    if step == "overfitting":
        # Mode 2 (saved portfolio_history) requires an explicit --n-trials.
        return [
            sys.executable,
            "scripts/run_all_overfitting.py",
            "--strategy",
            strategy_key,
            "--n-trials",
            str(_estimate_n_trials(strategy_key)),
        ]
    raise ValueError(f"Unknown step: {step}")


def _read_result_file(strategy_key: str, filename: str):
    path = RESULTS_DIR / "strategies" / strategy_key / filename
    if not path.exists():
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Job result read failed for {path.name}: {e}")
        return None


def _tail(text: str, lines: int = LOG_TAIL_LINES) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


def _run_job(job_id: str) -> None:
    with _jobs_lock:
        job = _jobs[job_id]

    _slots.acquire()
    try:
        job["state"] = "running"
        job["started_at"] = datetime.now().isoformat()
        _persist_job(job)
        log_dir = JOBS_DIR / job_id
        log_dir.mkdir(parents=True, exist_ok=True)

        for step in job["steps"]:
            job["current_step"] = step
            cmd = _step_command(step, job["strategy_key"])
            logger.info(f"Job {job_id}: running {step}: {' '.join(cmd)}")
            step_started = datetime.now()
            try:
                # Force UTF-8 stdout in children: several scripts print
                # unicode (₀, ✓) that crashes under Windows cp1252.
                env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
                proc = subprocess.run(
                    cmd,
                    cwd=str(BASE_DIR),
                    capture_output=True,
                    text=True,
                    timeout=STEP_TIMEOUT_S,
                    env=env,
                )
                exit_code = proc.returncode
                output = (proc.stdout or "") + "\n" + (proc.stderr or "")
            except subprocess.TimeoutExpired:
                exit_code = -1
                output = f"TIMEOUT: step exceeded {STEP_TIMEOUT_S}s"
            except Exception as e:
                exit_code = -1
                output = f"LAUNCH FAILED: {e}"

            log_path = log_dir / f"{step}.log"
            try:
                log_path.write_text(output, encoding="utf-8", errors="replace")
            except Exception:
                pass

            job["step_results"][step] = {
                "exit_code": exit_code,
                "seconds": (datetime.now() - step_started).total_seconds(),
                "log": str(log_path.relative_to(RESULTS_DIR)),
            }
            _persist_job(job)

            if exit_code != 0:
                job["state"] = "failed"
                job["error"] = {
                    "step": step,
                    "exit_code": exit_code,
                    "log_tail": _tail(output),
                }
                break
        else:
            job["state"] = "done"

        job["current_step"] = None
        job["finished_at"] = datetime.now().isoformat()
        _persist_job(job)
    finally:
        _slots.release()


@jobs_bp.route("/api/run/<strategy_key>", methods=["POST"])
def start_run(strategy_key: str):
    """
    Launch backtest/validate/overfitting for one strategy definition.

    Optional JSON body: {"steps": ["backtest", "validate", "overfitting"]}
    (any ordered subset; default is all three).
    """
    if not is_valid_strategy_key(strategy_key):
        return jsonify({"error": "invalid strategy key"}), 400
    if not _definition_exists(strategy_key):
        return (
            jsonify(
                {
                    "error": f"no strategy definition found for '{strategy_key}'",
                    "hint": "key must exist under strategy_definitions/"
                    "{allocations,composed,overlays,portfolios}/",
                }
            ),
            404,
        )

    body = request.get_json(silent=True) or {}
    steps = body.get("steps", list(ALL_STEPS))
    if not isinstance(steps, list) or not steps:
        return jsonify({"error": "steps must be a non-empty list"}), 400
    bad = [s for s in steps if s not in ALL_STEPS]
    if bad:
        return (
            jsonify({"error": f"unknown steps {bad}; valid: {list(ALL_STEPS)}"}),
            400,
        )

    job_id = uuid.uuid4().hex[:12]
    job = {
        "job_id": job_id,
        "strategy_key": strategy_key,
        "steps": steps,
        "state": "queued",
        "current_step": None,
        "step_results": {},
        "created_at": datetime.now().isoformat(),
        "started_at": None,
        "finished_at": None,
        "error": None,
    }
    with _jobs_lock:
        _jobs[job_id] = job
        # Bound memory: keep the newest 200 jobs.
        while len(_jobs) > 200:
            _jobs.popitem(last=False)
    _persist_job(job)

    threading.Thread(target=_run_job, args=(job_id,), daemon=True).start()

    return (
        jsonify(
            {
                "job_id": job_id,
                "strategy_key": strategy_key,
                "steps": steps,
                "state": "queued",
                "status_url": f"/api/run/status/{job_id}",
            }
        ),
        202,
    )


@jobs_bp.route("/api/run/status/<job_id>")
def run_status(job_id: str):
    """Job state; when done, embeds metrics/validation/overfitting results."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        return jsonify({"error": "unknown job id"}), 404

    payload = dict(job)
    if job["state"] == "done":
        key = job["strategy_key"]
        payload["results"] = {
            "metrics": _read_result_file(key, "metrics.json"),
            "validation": _read_result_file(key, "validation.json"),
            "overfitting": _read_result_file(key, "overfitting_analysis.json"),
        }
    return jsonify(payload)


@jobs_bp.route("/api/run/jobs")
def list_jobs():
    """Most recent jobs, newest first (state only, no embedded results)."""
    with _jobs_lock:
        jobs = list(_jobs.values())
    return jsonify(list(reversed(jobs)))
