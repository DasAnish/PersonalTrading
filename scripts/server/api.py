"""API endpoints for the dashboard server."""

import csv
import io

import numpy as np
import pandas as pd
from flask import Blueprint, Response, jsonify, request

from .data import RESULTS_DIR, list_strategy_keys, load_strategy_data

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
        rows.append(
            {
                "key": key,
                "name": info.get("name", key),
                "sharpe_ratio": metrics.get("sharpe_ratio"),
                "cagr": metrics.get("cagr") or metrics.get("annualized_return"),
                "max_drawdown": metrics.get("max_drawdown"),
                "volatility": metrics.get("annualized_volatility") or metrics.get("volatility"),
                "total_return": metrics.get("total_return"),
                "calmar_ratio": metrics.get("calmar_ratio"),
            }
        )
    return jsonify(rows)


@bp.route("/api/strategy/<strategy_key>")
def api_strategy(strategy_key: str):
    """Get full data for a specific strategy."""
    data = load_strategy_data(strategy_key)
    if not data:
        return jsonify({"error": f"Strategy {strategy_key} not found"}), 404
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

    values = pd.Series(
        [p["total_value"] for p in portfolio],
        index=pd.to_datetime(
            [p.get("date", p.get("timestamp")) for p in portfolio]
        ),
    )

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

    values = pd.Series(
        [p["total_value"] for p in portfolio],
        index=pd.to_datetime(
            [p.get("date", p.get("timestamp")) for p in portfolio]
        ),
    )
    returns = values.pct_change().dropna()

    if len(returns) < window:
        return jsonify({"error": f"Insufficient data for window={window}"}), 400

    results = []
    for i in range(window, len(returns) + 1):
        window_returns = returns.iloc[i - window : i]
        date = returns.index[i - 1]

        if metric == "sharpe":
            mean_r = window_returns.mean()
            std_r = window_returns.std()
            val = (mean_r / std_r * np.sqrt(252)) if std_r > 0 else 0
        elif metric == "volatility":
            val = window_returns.std() * np.sqrt(252) * 100
        elif metric == "sortino":
            downside = window_returns[window_returns < 0]
            down_std = np.sqrt((downside**2).mean()) if len(downside) > 0 else 0
            val = (
                (window_returns.mean() / down_std * np.sqrt(252)) if down_std > 0 else 0
            )
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
            "Content-Disposition": f"attachment; filename={strategy_key}_{export_type}.csv"
        },
    )


@bp.route("/api/compare")
def api_compare_multi():
    """Multi-strategy comparison: tracking error, info ratio, correlation matrix."""
    strategies_param = request.args.get("strategies", "")
    keys = [k.strip() for k in strategies_param.split(",") if k.strip()]

    if len(keys) < 2:
        return jsonify({"error": "Provide at least 2 strategies via ?strategies=k1,k2"}), 400

    returns_series = {}
    for key in keys:
        data = load_strategy_data(key)
        if not data:
            return jsonify({"error": f"Strategy not found: {key}"}), 404
        portfolio = data.get("portfolio_history", [])
        if not portfolio:
            return jsonify({"error": f"No portfolio history for: {key}"}), 404
        values = pd.Series(
            [p["total_value"] for p in portfolio],
            index=pd.to_datetime(
                [p.get("date", p.get("timestamp")) for p in portfolio]
            ),
        )
        returns_series[key] = values.pct_change().dropna()

    common = None
    for r in returns_series.values():
        common = r.index if common is None else common.intersection(r.index)

    if len(common) < 2:
        return jsonify({"error": "Insufficient overlapping data"}), 400

    aligned = {k: v[common] for k, v in returns_series.items()}
    key_list = list(aligned.keys())

    pairwise = []
    for i in range(len(key_list)):
        for j in range(i + 1, len(key_list)):
            k1, k2 = key_list[i], key_list[j]
            active = aligned[k1] - aligned[k2]
            te = float(active.std() * np.sqrt(252))
            ir = (
                float(active.mean() / active.std() * np.sqrt(252))
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

    values1 = pd.Series(
        [p["total_value"] for p in portfolio1],
        index=pd.to_datetime(
            [p.get("date", p.get("timestamp")) for p in portfolio1]
        ),
    )
    values2 = pd.Series(
        [p["total_value"] for p in portfolio2],
        index=pd.to_datetime(
            [p.get("date", p.get("timestamp")) for p in portfolio2]
        ),
    )

    common = values1.index.intersection(values2.index)
    if len(common) < 2:
        return jsonify({"error": "Insufficient overlapping data"}), 400

    returns1 = values1[common].pct_change().dropna()
    returns2 = values2[common].pct_change().dropna()

    active_returns = returns1 - returns2
    tracking_error = float(active_returns.std() * np.sqrt(252))
    info_ratio = (
        float(active_returns.mean() / active_returns.std() * np.sqrt(252))
        if active_returns.std() > 0
        else 0
    )

    relative = (values1[common] / values2[common]).dropna()
    relative_data = [
        {"date": d.isoformat(), "value": round(float(v), 4)} for d, v in relative.items()
    ]

    return jsonify(
        {
            "tracking_error": round(tracking_error * 100, 2),
            "information_ratio": round(info_ratio, 4),
            "relative_performance": relative_data,
        }
    )
