"""Unit tests for analytics/validation.py dataclasses, JSON safety, verdict rule."""

import json

from analytics.validation import (
    TestOutcome,
    ValidationResult,
    _json_safe,
    _overall_verdict,
)

# ---------------------------------------------------------------------------
# JSON Sanitisation (_json_safe)
# ---------------------------------------------------------------------------


class TestJsonSafe:
    def test_finite_float_rounded(self):
        result = _json_safe({"value": 0.123456789})
        assert result["value"] == 0.123457  # rounded to 6 decimals

    def test_infinity_to_none(self):
        result = _json_safe({"value": float("inf")})
        assert result["value"] is None

    def test_negative_infinity_to_none(self):
        result = _json_safe({"value": float("-inf")})
        assert result["value"] is None

    def test_nan_to_none(self):
        result = _json_safe({"value": float("nan")})
        assert result["value"] is None

    def test_nested_dict_recursive(self):
        data = {
            "metrics": {
                "sharpe": 1.234567,
                "inf_val": float("inf"),
                "nested": {"nan_val": float("nan")},
            }
        }
        result = _json_safe(data)
        assert result["metrics"]["sharpe"] == 1.234567
        assert result["metrics"]["inf_val"] is None
        assert result["metrics"]["nested"]["nan_val"] is None

    def test_list_recursive(self):
        data = [1.234567, float("inf"), float("nan"), {"nested": float("-inf")}]
        result = _json_safe(data)
        assert result[0] == 1.234567
        assert result[1] is None
        assert result[2] is None
        assert result[3]["nested"] is None

    def test_preserves_non_float_types(self):
        data = {"str": "hello", "int": 42, "bool": True, "none": None}
        result = _json_safe(data)
        assert result == data

    def test_json_dumps_succeeds(self):
        # Core test: ensure the output is JSON-serializable with no Infinity/NaN
        data = {
            "sharpe": 1.2345,
            "inf": float("inf"),
            "nan": float("nan"),
            "metrics": [0.5, float("-inf"), float("nan")],
        }
        safe_data = _json_safe(data)
        json_str = json.dumps(safe_data)
        assert "Infinity" not in json_str
        assert "NaN" not in json_str


# ---------------------------------------------------------------------------
# TestOutcome
# ---------------------------------------------------------------------------


class TestTestOutcome:
    def test_to_dict_sanitizes_values(self):
        outcome = TestOutcome(
            name="dsr",
            verdict="PASS",
            values={"sharpe": 1.234567, "inf_val": float("inf")},
            note="test",
        )
        d = outcome.to_dict()
        assert d["name"] == "dsr"
        assert d["verdict"] == "PASS"
        assert d["values"]["sharpe"] == 1.234567
        assert d["values"]["inf_val"] is None
        assert d["note"] == "test"

    def test_to_dict_json_serializable(self):
        outcome = TestOutcome(
            name="cpcv",
            verdict="WARN",
            values={"pct5": float("nan"), "mean": 0.5},
            note="",
        )
        json_str = json.dumps(outcome.to_dict())
        assert "NaN" not in json_str


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------


class TestValidationResult:
    def test_to_dict_structure(self):
        tests = [
            TestOutcome(name="dsr", verdict="PASS", values={"dsr": 0.9}),
            TestOutcome(name="minbtl", verdict="PASS", values={"min_years": 2.0}),
        ]
        result = ValidationResult(
            strategy_key="test_strat",
            generated="2026-01-15",
            tests=tests,
            overall="PASS",
        )
        d = result.to_dict()
        assert d["strategy_key"] == "test_strat"
        assert d["generated"] == "2026-01-15"
        assert len(d["tests"]) == 2
        assert d["overall"] == "PASS"

    def test_to_dict_json_serializable(self):
        tests = [
            TestOutcome(name="dsr", verdict="PASS", values={"inf": float("inf")}),
            TestOutcome(name="bootstrap", verdict="WARN", values={"nan": float("nan")}),
        ]
        result = ValidationResult(
            strategy_key="test",
            generated="2026-01-15",
            tests=tests,
            overall="WARN",
        )
        json_str = json.dumps(result.to_dict())
        assert "Infinity" not in json_str
        assert "NaN" not in json_str


# ---------------------------------------------------------------------------
# Overall Verdict Logic (_overall_verdict)
# ---------------------------------------------------------------------------


class TestOverallVerdict:
    def test_minbtl_fail_wins(self):
        """MinBTL FAIL -> overall FAIL even if everything else passes."""
        tests = [
            TestOutcome(name="minbtl", verdict="FAIL"),
            TestOutcome(name="dsr", verdict="PASS"),
            TestOutcome(name="cpcv", verdict="PASS"),
            TestOutcome(name="bootstrap", verdict="PASS"),
        ]
        assert _overall_verdict(tests) == "FAIL"

    def test_dsr_fail_wins(self):
        """DSR FAIL -> overall FAIL."""
        tests = [
            TestOutcome(name="dsr", verdict="FAIL"),
            TestOutcome(name="minbtl", verdict="PASS"),
            TestOutcome(name="cpcv", verdict="PASS"),
            TestOutcome(name="bootstrap", verdict="PASS"),
        ]
        assert _overall_verdict(tests) == "FAIL"

    def test_cpcv_fail_wins(self):
        """CPCV FAIL -> overall FAIL."""
        tests = [
            TestOutcome(name="cpcv", verdict="FAIL"),
            TestOutcome(name="dsr", verdict="PASS"),
            TestOutcome(name="minbtl", verdict="PASS"),
            TestOutcome(name="bootstrap", verdict="PASS"),
        ]
        assert _overall_verdict(tests) == "FAIL"

    def test_bootstrap_cannot_cause_fail(self):
        """Bootstrap FAIL should not happen (it caps out at WARN), but test anyway."""
        tests = [
            TestOutcome(name="bootstrap", verdict="WARN"),
            TestOutcome(name="dsr", verdict="PASS"),
            TestOutcome(name="minbtl", verdict="PASS"),
            TestOutcome(name="cpcv", verdict="PASS"),
        ]
        assert _overall_verdict(tests) == "WARN"

    def test_bootstrap_warn_pulls_to_warn(self):
        """Bootstrap WARN + rest PASS -> overall WARN."""
        tests = [
            TestOutcome(name="bootstrap", verdict="WARN"),
            TestOutcome(name="dsr", verdict="PASS"),
            TestOutcome(name="minbtl", verdict="PASS"),
            TestOutcome(name="cpcv", verdict="PASS"),
        ]
        assert _overall_verdict(tests) == "WARN"

    def test_any_skip_nonminbtl_pulls_to_warn(self):
        """SKIP on non-MinBTL tests -> overall at least WARN."""
        # DSR SKIP
        tests = [
            TestOutcome(name="dsr", verdict="SKIP"),
            TestOutcome(name="minbtl", verdict="PASS"),
            TestOutcome(name="cpcv", verdict="PASS"),
            TestOutcome(name="bootstrap", verdict="PASS"),
        ]
        assert _overall_verdict(tests) == "WARN"

        # CPCV SKIP
        tests = [
            TestOutcome(name="cpcv", verdict="SKIP"),
            TestOutcome(name="dsr", verdict="PASS"),
            TestOutcome(name="minbtl", verdict="PASS"),
            TestOutcome(name="bootstrap", verdict="PASS"),
        ]
        assert _overall_verdict(tests) == "WARN"

    def test_any_warn_pulls_to_warn(self):
        """Any WARN + no FAIL -> overall WARN."""
        tests = [
            TestOutcome(name="dsr", verdict="WARN"),
            TestOutcome(name="minbtl", verdict="PASS"),
            TestOutcome(name="cpcv", verdict="PASS"),
            TestOutcome(name="bootstrap", verdict="PASS"),
        ]
        assert _overall_verdict(tests) == "WARN"

    def test_all_pass_returns_pass(self):
        """All PASS -> overall PASS."""
        tests = [
            TestOutcome(name="dsr", verdict="PASS"),
            TestOutcome(name="minbtl", verdict="PASS"),
            TestOutcome(name="cpcv", verdict="PASS"),
            TestOutcome(name="bootstrap", verdict="PASS"),
        ]
        assert _overall_verdict(tests) == "PASS"
