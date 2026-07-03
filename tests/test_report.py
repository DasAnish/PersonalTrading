"""
Tests for analytics/report.py.

Builds fixture ``results/strategies/<key>/`` directories directly under
``tmp_path`` (mirroring the on-disk shapes written by
``backtesting.results_io.save_strategy_results``,
``analytics.stress_testing.StressTestReport.to_dict()``, and
``analytics.overfitting.overfitting_analysis_to_dict()``) and asserts:

- a "full" strategy (metrics + stress_test + overfitting_analysis present)
  produces a report with every section populated;
- a "sparse" strategy (metrics.json only) produces a report where the
  optional sections are replaced by a note, without raising;
- write_report() actually writes report.md (and report.html when asked);
- to_html() produces a self-contained document.
"""

import json

import pytest

from analytics.report import build_report, to_html, write_report
from backtesting.results_schema import (
    OVERFITTING_FILE,
    STRESS_TEST_FILE,
    strategy_dir,
)


def _metrics_json() -> dict:
    return {
        "total_return": 0.452,
        "cagr": 0.081,
        "sharpe_ratio": 1.12,
        "sortino_ratio": 1.4,
        "calmar_ratio": 0.9,
        "max_drawdown": -0.183,
        "volatility": 0.14,
        "var_95": -0.02,
        "cvar_95": -0.031,
        "final_value": 14_500.23,
        "initial_value": 10_000.0,
        "total_transactions": 42,
    }


def _info_json() -> dict:
    return {
        "key": "hrp_ward",
        "display_name": "HRP (Ward Linkage)",
        "type": "allocation",
        "description": "Hierarchical risk parity with Ward linkage.",
    }


def _portfolio_history_json() -> list:
    return [
        {"date": "2021-01-04T00:00:00", "total_value": 10_000.0},
        {"date": "2021-02-01T00:00:00", "total_value": 10_250.0},
        {"date": "2022-06-01T00:00:00", "total_value": 14_500.23},
    ]


def _stress_test_json() -> dict:
    return {
        "strategy_name": "HRP (Ward Linkage)",
        "crisis_metrics": [
            {
                "crisis_name": "2020 COVID",
                "crisis_description": "COVID-19 pandemic crash",
                "start": "2020-02-19",
                "end": "2020-03-31",
                "total_return_pct": -12.5,
                "annualised_return_pct": -55.0,
                "max_drawdown_pct": -18.3,
                "recovery_days": 90,
                "sharpe": -1.2,
                "has_data": True,
            }
        ],
        "scenario_removal": [
            {
                "crisis_name": "2020 COVID",
                "full_sharpe": 1.12,
                "loo_sharpe": 1.30,
                "sharpe_delta": -0.18,
            }
        ],
    }


def _overfitting_analysis_json() -> dict:
    return {
        "strategy_key": "hrp_ward",
        "analysis_date": "2026-06-01T12:00:00",
        "n_param_combinations": 3,
        "config": {},
        "errors": [],
        "dsr": {
            "dsr": 0.873,
            "observed_sharpe": 1.12,
            "sharpe_reference": 0.65,
            "n_trials": 3,
            "t_periods": 500,
            "skewness": -0.2,
            "excess_kurtosis": 1.1,
            "verdict": "WARN",
            "threshold_pass": 0.95,
            "threshold_warn": 0.80,
        },
        "pbo": {
            "pbo": 0.25,
            "prob_oos_loss": 0.30,
            "n_combinations": 12870,
            "s_subsets": 16,
            "n_configs": 3,
            "logit_scores": [0.1, -0.2, 0.5, 0.3],
            "verdict": "PASS",
            "threshold_pass": 0.30,
            "threshold_warn": 0.50,
        },
        "kfold": {
            "n_folds": 5,
            "fold_sharpes": [1.1, 0.9, -0.2, 1.4, 0.8],
            "mean_sharpe": 0.8,
            "std_sharpe": 0.6,
            "fraction_positive": 0.8,
            "worst_fold_sharpe": -0.2,
            "verdict": "PASS",
            "threshold_pass": 0.6,
            "threshold_warn": 0.4,
        },
    }


def _write_full_strategy(results_dir, key="hrp_ward") -> None:
    target_dir = strategy_dir(results_dir, key)
    target_dir.mkdir(parents=True, exist_ok=True)
    with open(target_dir / "metrics.json", "w") as f:
        json.dump(_metrics_json(), f)
    with open(target_dir / "info.json", "w") as f:
        json.dump(_info_json(), f)
    with open(target_dir / "portfolio_history.json", "w") as f:
        json.dump(_portfolio_history_json(), f)
    with open(target_dir / STRESS_TEST_FILE, "w") as f:
        json.dump(_stress_test_json(), f)
    with open(target_dir / OVERFITTING_FILE, "w") as f:
        json.dump(_overfitting_analysis_json(), f)


def _write_sparse_strategy(results_dir, key="sparse_strategy") -> None:
    target_dir = strategy_dir(results_dir, key)
    target_dir.mkdir(parents=True, exist_ok=True)
    with open(target_dir / "metrics.json", "w") as f:
        json.dump(_metrics_json(), f)


# ---------------------------------------------------------------------------
# build_report
# ---------------------------------------------------------------------------


def test_build_report_full_strategy_includes_all_sections(tmp_path):
    _write_full_strategy(tmp_path)

    report = build_report("hrp_ward", tmp_path)

    assert "# HRP (Ward Linkage)" in report
    assert "## Performance Metrics" in report
    assert "Sharpe Ratio" in report
    assert "## Stress Testing" in report
    assert "Crisis Period Performance" in report
    assert "2020 COVID" in report
    assert "Scenario Removal (Leave-One-Crisis-Out)" in report
    assert "## Overfitting Analysis" in report
    assert "Deflated Sharpe Ratio (DSR)" in report
    assert "Probability of Backtest Overfitting (PBO)" in report
    assert "K-Fold Temporal Stability" in report
    assert "## Data Completeness" in report
    assert "present" in report


def test_build_report_sparse_strategy_notes_missing_sections(tmp_path):
    _write_sparse_strategy(tmp_path)

    report = build_report("sparse_strategy", tmp_path)

    # Metrics section is present.
    assert "## Performance Metrics" in report
    assert "Sharpe Ratio" in report

    # Stress test / overfitting sections are present but noted as absent,
    # not raising and not fabricating data.
    assert "## Stress Testing" in report
    assert "Stress test not run" in report
    assert "## Overfitting Analysis" in report
    assert "Overfitting analysis not run" in report

    assert "## Data Completeness" in report
    assert "absent" in report


def test_build_report_never_raises_on_nonexistent_strategy(tmp_path):
    """A strategy dir that doesn't exist at all still returns a report string."""
    report = build_report("does_not_exist", tmp_path)
    assert "# " in report
    assert "## Performance Metrics" in report
    assert "metrics.json not found" in report


def test_build_report_metrics_table_has_rows(tmp_path):
    _write_full_strategy(tmp_path)
    report = build_report("hrp_ward", tmp_path)
    # Every metric key should appear (humanized) in the metrics table.
    assert "Total Return" in report
    assert "Max Drawdown" in report
    assert "Cagr" in report or "CAGR" in report


# ---------------------------------------------------------------------------
# write_report
# ---------------------------------------------------------------------------


def test_write_report_creates_markdown_file(tmp_path):
    _write_full_strategy(tmp_path)

    written = write_report("hrp_ward", tmp_path, fmt="md")

    assert written["md"] is not None
    assert written["html"] is None
    assert written["md"].exists()
    assert written["md"] == strategy_dir(tmp_path, "hrp_ward") / "report.md"
    content = written["md"].read_text()
    assert "# HRP (Ward Linkage)" in content


def test_write_report_both_formats(tmp_path):
    _write_full_strategy(tmp_path)

    written = write_report("hrp_ward", tmp_path, fmt="both")

    assert written["md"].exists()
    assert written["html"].exists()
    assert written["html"] == strategy_dir(tmp_path, "hrp_ward") / "report.html"


def test_write_report_invalid_fmt_raises(tmp_path):
    _write_full_strategy(tmp_path)
    with pytest.raises(ValueError):
        write_report("hrp_ward", tmp_path, fmt="pdf")


def test_write_report_sparse_strategy_does_not_crash(tmp_path):
    _write_sparse_strategy(tmp_path)
    written = write_report("sparse_strategy", tmp_path, fmt="md")
    assert written["md"].exists()


# ---------------------------------------------------------------------------
# to_html
# ---------------------------------------------------------------------------


def test_to_html_is_self_contained(tmp_path):
    _write_full_strategy(tmp_path)
    report = build_report("hrp_ward", tmp_path)

    doc = to_html(report)

    assert "<html" in doc
    assert "</html>" in doc
    assert "<style>" in doc
    # No external resources — script tags, stylesheet links, or remote src/href.
    assert "<script" not in doc
    assert "http://" not in doc
    assert "https://" not in doc
    assert "<link" not in doc


def test_to_html_renders_headers_and_tables(tmp_path):
    _write_full_strategy(tmp_path)
    report = build_report("hrp_ward", tmp_path)
    doc = to_html(report)

    assert "<h1>" in doc
    assert "<h2>" in doc
    assert "<table>" in doc
    assert "<th>" in doc
