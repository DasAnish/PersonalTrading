"""Dashboard API for strategy pre-registrations (analytics/registrations.py).

Register freezes a strategy's promotion metrics + kill criteria; the nightly
(scripts/check_registrations.py) grades them against realized drawdowns. This
module only reads/writes the registration store and the nightly status file —
it never trades.
"""

import json
from pathlib import Path

from flask import Blueprint, jsonify, request

from analytics.registrations import (
    backtest_block_from_metrics,
    load_all_registrations,
    register,
    remove_registration,
)
from backtesting.results_schema import STRATEGY_FILES, strategy_dir

from .jobs import _definition_exists

registrations_bp = Blueprint("registrations", __name__)

RESULTS_DIR = Path("results")
STATUS_PATH = RESULTS_DIR / "registration_status.json"


def _load_status() -> dict:
    if not STATUS_PATH.exists():
        return {}
    try:
        return json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _metrics_for(strategy: str) -> dict | None:
    path = strategy_dir(RESULTS_DIR, strategy) / STRATEGY_FILES["metrics"]
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


@registrations_bp.route("/api/registrations")
def api_registrations():
    """All registrations, each enriched with its latest nightly status."""
    status = _load_status()
    out = []
    for reg in load_all_registrations():
        entry = dict(reg)
        entry["status"] = status.get(reg["strategy"], {"status": "unknown"})
        out.append(entry)
    return jsonify(out)


@registrations_bp.route("/api/registrations", methods=["POST"])
def api_register():
    """Register a strategy, prefilling frozen backtest metrics from metrics.json."""
    body = request.get_json(silent=True) or {}
    strategy = body.get("strategy")
    if not strategy or not _definition_exists(strategy):
        return jsonify({"error": f"unknown strategy: {strategy!r}"}), 400

    metrics = _metrics_for(strategy)
    if metrics is None:
        return (
            jsonify({"error": f"no metrics.json for {strategy!r} — run its backtest"}),
            400,
        )

    backtest = backtest_block_from_metrics(metrics)
    entry = register(
        strategy,
        backtest,
        kill_criteria=body.get("kill_criteria"),
        review_date=body.get("review_date"),
    )
    return jsonify(entry), 201


@registrations_bp.route("/api/registrations/<strategy>", methods=["DELETE"])
def api_remove_registration(strategy):
    if not remove_registration(strategy):
        return jsonify({"error": f"not registered: {strategy}"}), 404
    return jsonify({"removed": strategy})
