"""API endpoints for the dashboard server."""

import csv
import io
import json

import numpy as np
import pandas as pd
from flask import Blueprint, Response, jsonify, request

from analytics.metrics import (
    calculate_cagr,
    calculate_omega_ratio,
    infer_periods_per_year,
)

from .data import (
    RESULTS_DIR,
    build_validation_summary,
    history_to_series,
    is_valid_strategy_key,
    list_strategy_keys,
    load_strategy_data,
    load_overfitting_analysis,
    load_strategy_tags,
    load_stress_test,
    load_validation,
)

MAX_COMPARE_STRATEGIES = 10


def _cagr_from_history(portfolio_history: list) -> float | None:
    """Compute CAGR from portfolio history via analytics.metrics.calculate_cagr."""
    series = history_to_series(portfolio_history)
    if len(series) < 2:
        return None
    years = (series.index[-1] - series.index[0]).days / 365.25
    if years <= 0:
        return None
    return calculate_cagr(series)


def _omega_from_history(portfolio_history: list) -> float | None:
    """Compute omega ratio via analytics.metrics.calculate_omega_ratio."""
    series = history_to_series(portfolio_history)
    if len(series) < 2:
        return None
    returns = series.pct_change().dropna()
    if len(returns) == 0:
        return None
    omega = calculate_omega_ratio(returns)
    if not np.isfinite(omega):
        return None
    return round(omega, 4)


bp = Blueprint("api", __name__)


@bp.route("/api/strategies")
def api_strategies():
    """List available strategy keys."""
    return jsonify(list_strategy_keys())


@bp.route("/api/strategies/summary")
def api_strategies_summary():
    """Return key metrics for all strategies (used by overview page)."""
    keys = list_strategy_keys()
    rows = []
    for key in keys:
        data = load_strategy_data(key)
        if not data:
            continue
        metrics = data.get("metrics", {})
        info = data.get("info", {})
        portfolio_history = data.get("portfolio_history", [])
        total_return = metrics.get("total_return")
        max_drawdown = metrics.get("max_drawdown")

        cagr = metrics.get("cagr") or metrics.get("annualized_return")
        if cagr is None and total_return is not None:
            cagr = _cagr_from_history(portfolio_history)

        calmar = metrics.get("calmar_ratio")
        if calmar is None and cagr is not None and max_drawdown and max_drawdown != 0:
            calmar = round(cagr / abs(max_drawdown), 4)

        omega = metrics.get("omega_ratio") or _omega_from_history(portfolio_history)

        rows.append(
            {
                "key": key,
                "name": info.get("name", key),
                "description": info.get("description", ""),
                "tags": load_strategy_tags(key),
                "sharpe_ratio": metrics.get("sharpe_ratio"),
                "cagr": cagr,
                "max_drawdown": max_drawdown,
                "volatility": metrics.get("annualized_volatility")
                or metrics.get("volatility"),
                "total_return": total_return,
                "calmar_ratio": calmar,
                "omega_ratio": omega,
            }
        )
    return jsonify(rows)


@bp.route("/api/strategy/<strategy_key>")
def api_strategy(strategy_key: str):
    """Get full data for a specific strategy."""
    data = load_strategy_data(strategy_key)
    if not data:
        return jsonify({"error": f"Strategy {strategy_key} not found"}), 404

    metrics = data.get("metrics", {})
    portfolio_history = data.get("portfolio_history", [])
    total_return = metrics.get("total_return")
    max_drawdown = metrics.get("max_drawdown")

    if "cagr" not in metrics and total_return is not None:
        cagr = _cagr_from_history(portfolio_history)
        if cagr is not None:
            metrics["cagr"] = cagr

    if "calmar_ratio" not in metrics:
        cagr = metrics.get("cagr")
        if cagr is not None and max_drawdown and max_drawdown != 0:
            metrics["calmar_ratio"] = round(cagr / abs(max_drawdown), 4)

    if "omega_ratio" not in metrics:
        omega = _omega_from_history(portfolio_history)
        if omega is not None:
            metrics["omega_ratio"] = omega

    validation = load_validation(strategy_key)
    if validation is not None:
        data["validation"] = validation

    return jsonify(data)


@bp.route("/api/strategy/<strategy_key>/monthly_returns")
def api_monthly_returns(strategy_key: str):
    """Monthly returns heatmap data."""
    data = load_strategy_data(strategy_key)
    if not data:
        return jsonify({"error": f"Strategy {strategy_key} not found"}), 404

    portfolio = data.get("portfolio_history", [])
    if not portfolio:
        return jsonify({"error": "No portfolio history"}), 404

    values = history_to_series(portfolio)

    monthly = values.resample("ME").last()
    monthly_returns = monthly.pct_change().dropna()

    result = [
        {"year": int(d.year), "month": int(d.month), "return": round(float(r) * 100, 2)}
        for d, r in monthly_returns.items()
    ]
    return jsonify(result)


@bp.route("/api/strategy/<strategy_key>/rolling")
def api_rolling_metrics(strategy_key: str):
    """Rolling Sharpe / volatility / Sortino data."""
    data = load_strategy_data(strategy_key)
    if not data:
        return jsonify({"error": f"Strategy {strategy_key} not found"}), 404

    metric = request.args.get("metric", "sharpe")
    window = int(request.args.get("window", 63))

    portfolio = data.get("portfolio_history", [])
    if not portfolio:
        return jsonify({"error": "No portfolio history"}), 404

    values = history_to_series(portfolio)
    returns = values.pct_change().dropna()

    if len(returns) < window:
        return jsonify({"error": f"Insufficient data for window={window}"}), 400

    # Portfolio history is a rebalance-period series (usually monthly) —
    # annualize by its actual spacing, never a hard-coded 252.
    ppy = infer_periods_per_year(values.index)
    ann = np.sqrt(ppy)

    results = []
    for i in range(window, len(returns) + 1):
        window_returns = returns.iloc[i - window : i]
        date = returns.index[i - 1]

        if metric == "sharpe":
            mean_r = window_returns.mean()
            std_r = window_returns.std()
            val = (mean_r / std_r * ann) if std_r > 0 else 0
        elif metric == "volatility":
            val = window_returns.std() * ann * 100
        elif metric == "sortino":
            downside = window_returns[window_returns < 0]
            down_std = np.sqrt((downside**2).mean()) if len(downside) > 0 else 0
            val = (window_returns.mean() / down_std * ann) if down_std > 0 else 0
        else:
            val = 0

        results.append({"date": date.isoformat(), "value": round(float(val), 4)})

    return jsonify({"metric": metric, "window": window, "data": results})


@bp.route("/api/strategy/<strategy_key>/export")
def api_export(strategy_key: str):
    """Export strategy data as CSV."""
    data = load_strategy_data(strategy_key)
    if not data:
        return jsonify({"error": f"Strategy {strategy_key} not found"}), 404

    export_type = request.args.get("type", "portfolio")
    type_map = {
        "portfolio": "portfolio_history",
        "transactions": "transactions",
        "weights": "weights_history",
    }

    if export_type not in type_map:
        return jsonify({"error": f"Unknown export type: {export_type}"}), 400

    rows = data.get(type_map[export_type], [])
    if not rows:
        return jsonify({"error": "No data to export"}), 404

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": (
                f"attachment; filename={strategy_key}_{export_type}.csv"
            )
        },
    )


@bp.route("/api/strategy/<strategy_key>/overfitting")
def api_overfitting(strategy_key: str):
    """
    Get overfitting analysis (DSR + PBO) for a strategy.

    Returns the contents of overfitting_analysis.json if it exists.
    Returns 404 with a helpful message if the analysis has not been run yet.
    """
    analysis = load_overfitting_analysis(strategy_key)
    if analysis is None:
        return (
            jsonify(
                {
                    "error": "Overfitting analysis not found.",
                    "hint": (
                        f"Run: python scripts/run_all_overfitting.py "
                        f"--strategy {strategy_key} --n-trials <N>"
                    ),
                }
            ),
            404,
        )
    return jsonify(analysis)


@bp.route("/api/strategy/<strategy_key>/stress_test")
def api_stress_test(strategy_key: str):
    """
    Get stress-test results for a strategy.

    Returns the contents of stress_test.json if it exists.
    Returns 404 with a hint if the backtest was not run with --stress-test.
    """
    data = load_stress_test(strategy_key)
    if data is None:
        return (
            jsonify(
                {
                    "error": "Stress test results not found.",
                    "hint": ("Run: python scripts/run_backtest.py --all --stress-test"),
                }
            ),
            404,
        )
    return jsonify(data)


@bp.route("/api/compare")
def api_compare_multi():
    """Multi-strategy comparison: tracking error, info ratio, correlation matrix."""
    strategies_param = request.args.get("strategies", "")
    keys = [k.strip() for k in strategies_param.split(",") if k.strip()]

    if len(keys) < 2:
        return (
            jsonify({"error": "Provide at least 2 strategies via ?strategies=k1,k2"}),
            400,
        )

    if len(keys) > MAX_COMPARE_STRATEGIES:
        return (
            jsonify(
                {
                    "error": (
                        f"Too many strategies requested ({len(keys)}). "
                        f"Maximum is {MAX_COMPARE_STRATEGIES}."
                    )
                }
            ),
            400,
        )

    invalid_keys = [k for k in keys if not is_valid_strategy_key(k)]
    if invalid_keys:
        return jsonify({"error": f"Invalid strategy key(s): {invalid_keys}"}), 400

    returns_series = {}
    for key in keys:
        data = load_strategy_data(key)
        if not data:
            return jsonify({"error": f"Strategy not found: {key}"}), 404
        portfolio = data.get("portfolio_history", [])
        if not portfolio:
            return jsonify({"error": f"No portfolio history for: {key}"}), 404
        values = history_to_series(portfolio)
        returns_series[key] = values.pct_change().dropna()

    common = None
    for r in returns_series.values():
        common = r.index if common is None else common.intersection(r.index)

    if len(common) < 2:
        return jsonify({"error": "Insufficient overlapping data"}), 400

    aligned = {k: v[common] for k, v in returns_series.items()}
    key_list = list(aligned.keys())

    ppy = infer_periods_per_year(common)
    ann_sqrt = np.sqrt(ppy)

    pairwise = []
    for i in range(len(key_list)):
        for j in range(i + 1, len(key_list)):
            k1, k2 = key_list[i], key_list[j]
            active = aligned[k1] - aligned[k2]
            te = float(active.std() * ann_sqrt)
            ir = (
                float(active.mean() / active.std() * ann_sqrt)
                if active.std() > 0
                else 0
            )
            pairwise.append(
                {
                    "strategy1": k1,
                    "strategy2": k2,
                    "tracking_error": round(te * 100, 2),
                    "information_ratio": round(ir, 4),
                }
            )

    df_returns = pd.DataFrame(aligned)
    corr = df_returns.corr()
    correlation_matrix = {
        k: {k2: round(float(v), 4) for k2, v in row.items()}
        for k, row in corr.to_dict().items()
    }

    return jsonify(
        {
            "strategies": key_list,
            "pairwise": pairwise,
            "correlation_matrix": correlation_matrix,
        }
    )


@bp.route("/api/compare/<key1>/<key2>")
def api_compare(key1: str, key2: str):
    """Comparison metrics between two specific strategies."""
    data1 = load_strategy_data(key1)
    data2 = load_strategy_data(key2)

    if not data1 or not data2:
        return jsonify({"error": "One or both strategies not found"}), 404

    portfolio1 = data1.get("portfolio_history", [])
    portfolio2 = data2.get("portfolio_history", [])

    if not portfolio1 or not portfolio2:
        return jsonify({"error": "Missing portfolio history"}), 404

    values1 = history_to_series(portfolio1)
    values2 = history_to_series(portfolio2)

    common = values1.index.intersection(values2.index)
    if len(common) < 2:
        return jsonify({"error": "Insufficient overlapping data"}), 400

    returns1 = values1[common].pct_change().dropna()
    returns2 = values2[common].pct_change().dropna()

    ppy = infer_periods_per_year(common)
    ann_sqrt = np.sqrt(ppy)

    active_returns = returns1 - returns2
    tracking_error = float(active_returns.std() * ann_sqrt)
    info_ratio = (
        float(active_returns.mean() / active_returns.std() * ann_sqrt)
        if active_returns.std() > 0
        else 0
    )

    relative = (values1[common] / values2[common]).dropna()
    relative_data = [
        {"date": d.isoformat(), "value": round(float(v), 4)}
        for d, v in relative.items()
    ]

    return jsonify(
        {
            "tracking_error": round(tracking_error * 100, 2),
            "information_ratio": round(info_ratio, 4),
            "relative_performance": relative_data,
        }
    )


@bp.route("/api/validation-summary")
def api_validation_summary():
    """Library-wide validation battery + SPA/Reality-Check summary for the panel."""
    return jsonify(build_validation_summary())


def _read_results_json(filename: str):
    """Best-effort read of a top-level results/ JSON report, else None."""
    path = RESULTS_DIR / filename
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


@bp.route("/api/data-freshness")
def api_data_freshness():
    """
    Cache freshness + last pipeline run, for the dashboard banner.

    Reads results/cache_validation.json and results/run_manifest.json
    (both produced by scripts/run_nightly.py and its pieces). The point is
    to make silent data rot visible: a stale panel end silently truncates
    every backtest to that date (the AIGC failure mode).
    """
    validation = _read_results_json("cache_validation.json")
    manifest = _read_results_json("run_manifest.json")

    payload = {"available": validation is not None or manifest is not None}
    if validation is not None:
        payload["cache"] = {
            "as_of": validation.get("as_of"),
            "panel_end": validation.get("panel_end"),
            "panel_stale_days": validation.get("panel_stale_days"),
            "gate_failed": validation.get("gate_failed"),
            "stale": validation.get("stale", []),
            "missing": validation.get("missing", []),
            "corrupt": validation.get("corrupt", []),
        }
    if manifest is not None:
        payload["last_run"] = {
            "run_id": manifest.get("run_id"),
            "started_at": manifest.get("started_at"),
            "ok": manifest.get("ok"),
            "data_refreshed": manifest.get("data_refreshed"),
            "total_strategies": manifest.get("total_strategies"),
        }

    # Results vintage: mixed data-end dates across strategies mean the
    # library was part-rebuilt against a different panel — rankings and
    # comparisons are unreliable until a full re-run.
    index = _read_results_json("strategies_index.json")
    if index is not None and index.get("vintage"):
        payload["results_vintage"] = index["vintage"]
        payload["available"] = True
    return jsonify(payload)
