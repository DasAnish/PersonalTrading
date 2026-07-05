"""Tests for analytics/validation.py — one-shot validation battery."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from analytics.validation import (
    TestOutcome,
    ValidationResult,
    _overall_verdict,
    run_validation_battery,
)
from backtesting.results_schema import STRATEGY_FILES

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _synthetic_monthly_returns(
    n: int = 84, mean: float = 0.008, std: float = 0.04, seed: int = 42
) -> pd.Series:
    """Generate n monthly returns with positive drift."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2012-01-31", periods=n, freq="ME")
    returns = pd.Series(rng.normal(mean, std, n), index=idx, name="returns")
    return returns


def _write_synthetic_portfolio(
    tmp_path: Path, strategy_key: str, n_months: int = 84
) -> Path:
    """
    Write a synthetic portfolio_history.json into tmp_path/strategies/<key>/.

    Returns the path to the strategy directory.
    Creates a random-walk equity curve with positive drift (like a good strategy).
    """
    returns = _synthetic_monthly_returns(n=n_months)
    initial_value = 100000.0
    values = [initial_value * v for v in (1.0 + returns).cumprod()]

    strategy_dir = tmp_path / "strategies" / strategy_key
    strategy_dir.mkdir(parents=True, exist_ok=True)

    portfolio_path = strategy_dir / STRATEGY_FILES["portfolio_history"]
    data = [
        {"date": str(pd.Timestamp(d).date()), "total_value": float(v)}
        for d, v in zip(returns.index, values)
    ]
    with open(portfolio_path, "w") as f:
        json.dump(data, f)

    return strategy_dir


@pytest.fixture
def synthetic_strategy(tmp_path):
    """Fixture: a full synthetic strategy with ~84 months of data."""
    return _write_synthetic_portfolio(tmp_path, "test_strategy", n_months=84)


@pytest.fixture
def short_history_strategy(tmp_path):
    """Fixture: a strategy with only ~8 months of data (should SKIP most tests)."""
    return _write_synthetic_portfolio(tmp_path, "short_strategy", n_months=8)


# ---------------------------------------------------------------------------
# run_validation_battery — successful runs
# ---------------------------------------------------------------------------


class TestRunValidationBattery:
    def test_returns_validation_result(self, synthetic_strategy, tmp_path):
        """Battery returns a valid ValidationResult with the right structure."""
        result = run_validation_battery(
            strategy_key="test_strategy",
            results_dir=tmp_path,
            n_trials=5,
            cpcv_folds=4,
            bootstrap_n=50,
        )
        assert isinstance(result, ValidationResult)
        assert result.strategy_key == "test_strategy"
        assert result.generated is not None
        assert len(result.tests) == 4
        assert result.overall in ("PASS", "WARN", "FAIL", "SKIP")

    def test_four_tests_present(self, synthetic_strategy, tmp_path):
        """Result contains exactly 4 tests: dsr, minbtl, cpcv, bootstrap."""
        result = run_validation_battery(
            strategy_key="test_strategy",
            results_dir=tmp_path,
            n_trials=5,
            cpcv_folds=4,
            bootstrap_n=50,
        )
        test_names = {t.name for t in result.tests}
        assert test_names == {"dsr", "minbtl", "cpcv", "bootstrap"}

    def test_all_verdicts_valid(self, synthetic_strategy, tmp_path):
        """Each test verdict is one of PASS/WARN/FAIL/SKIP."""
        result = run_validation_battery(
            strategy_key="test_strategy",
            results_dir=tmp_path,
            n_trials=5,
            cpcv_folds=4,
            bootstrap_n=50,
        )
        for test in result.tests:
            assert test.verdict in ("PASS", "WARN", "FAIL", "SKIP")

    def test_minbtl_always_runs(self, synthetic_strategy, tmp_path):
        """MinBTL never SKIP; it always produces a verdict."""
        result = run_validation_battery(
            strategy_key="test_strategy",
            results_dir=tmp_path,
            n_trials=5,
            cpcv_folds=4,
            bootstrap_n=50,
        )
        minbtl_test = next((t for t in result.tests if t.name == "minbtl"), None)
        assert minbtl_test is not None
        assert minbtl_test.verdict != "SKIP"

    def test_minbtl_has_required_values(self, synthetic_strategy, tmp_path):
        """MinBTL values dict contains min_years, actual_years, n_trials, observed_sharpe."""
        result = run_validation_battery(
            strategy_key="test_strategy",
            results_dir=tmp_path,
            n_trials=5,
            cpcv_folds=4,
            bootstrap_n=50,
        )
        minbtl_test = next(t for t in result.tests if t.name == "minbtl")
        assert "min_years" in minbtl_test.values
        assert "actual_years" in minbtl_test.values
        assert "n_trials" in minbtl_test.values
        assert "observed_sharpe" in minbtl_test.values

    def test_json_serializable(self, synthetic_strategy, tmp_path):
        """Result.to_dict() is JSON-serializable with no Infinity/NaN."""
        result = run_validation_battery(
            strategy_key="test_strategy",
            results_dir=tmp_path,
            n_trials=5,
            cpcv_folds=4,
            bootstrap_n=50,
        )
        d = result.to_dict()
        json_str = json.dumps(d)
        assert "Infinity" not in json_str
        assert "NaN" not in json_str


# ---------------------------------------------------------------------------
# run_validation_battery — short history behavior
# ---------------------------------------------------------------------------


class TestShortHistory:
    def test_short_history_dsr_skips(self, short_history_strategy, tmp_path):
        """With ~8 months, DSR should SKIP."""
        result = run_validation_battery(
            strategy_key="short_strategy",
            results_dir=tmp_path,
            n_trials=5,
            cpcv_folds=4,
            bootstrap_n=50,
        )
        dsr_test = next(t for t in result.tests if t.name == "dsr")
        assert dsr_test.verdict == "SKIP"

    def test_short_history_minbtl_runs(self, short_history_strategy, tmp_path):
        """With ~8 months, MinBTL still runs (may WARN or FAIL, but not SKIP)."""
        result = run_validation_battery(
            strategy_key="short_strategy",
            results_dir=tmp_path,
            n_trials=5,
            cpcv_folds=4,
            bootstrap_n=50,
        )
        minbtl_test = next(t for t in result.tests if t.name == "minbtl")
        assert minbtl_test.verdict != "SKIP"

    def test_short_history_cpcv_skips(self, short_history_strategy, tmp_path):
        """With ~8 months, CPCV should SKIP (too few observations for 4 folds)."""
        result = run_validation_battery(
            strategy_key="short_strategy",
            results_dir=tmp_path,
            n_trials=5,
            cpcv_folds=4,
            bootstrap_n=50,
        )
        cpcv_test = next(t for t in result.tests if t.name == "cpcv")
        assert cpcv_test.verdict == "SKIP"

    def test_short_history_bootstrap_skips(self, short_history_strategy, tmp_path):
        """With ~8 months (< 12), bootstrap should SKIP."""
        result = run_validation_battery(
            strategy_key="short_strategy",
            results_dir=tmp_path,
            n_trials=5,
            cpcv_folds=4,
            bootstrap_n=50,
        )
        bootstrap_test = next(t for t in result.tests if t.name == "bootstrap")
        assert bootstrap_test.verdict == "SKIP"

    def test_short_history_overall_at_least_warn(
        self, short_history_strategy, tmp_path
    ):
        """With short history and skips, overall should be WARN (never PASS)."""
        result = run_validation_battery(
            strategy_key="short_strategy",
            results_dir=tmp_path,
            n_trials=5,
            cpcv_folds=4,
            bootstrap_n=50,
        )
        # With multiple SKIPs, overall should be WARN
        assert result.overall in ("WARN", "FAIL")


# ---------------------------------------------------------------------------
# run_validation_battery — error handling
# ---------------------------------------------------------------------------


class TestRunValidationBatteryErrors:
    def test_missing_strategy_raises_filenotfounderror(self, tmp_path):
        """FileNotFoundError when strategy portfolio_history.json is missing."""
        with pytest.raises(FileNotFoundError) as excinfo:
            run_validation_battery(
                strategy_key="nonexistent_strategy",
                results_dir=tmp_path,
                n_trials=5,
            )
        assert "nonexistent_strategy" in str(excinfo.value)
        assert "portfolio_history.json" in str(excinfo.value).lower()

    def test_n_trials_floored_at_2(self, synthetic_strategy, tmp_path):
        """n_trials < 2 is floored to 2 (logged as warning)."""
        result = run_validation_battery(
            strategy_key="test_strategy",
            results_dir=tmp_path,
            n_trials=1,  # Will be floored to 2
            cpcv_folds=4,
            bootstrap_n=50,
        )
        minbtl_test = next(t for t in result.tests if t.name == "minbtl")
        assert minbtl_test.values["n_trials"] == 2


# ---------------------------------------------------------------------------
# Monkeypatch-based verdict rule testing
# ---------------------------------------------------------------------------


class TestOverallVerdictRulesMonkeypatch:
    """Test the full verdict composition by patching the underlying analytics."""

    def test_minbtl_fail_rule_via_direct_construction(self):
        """Construct TestOutcome objects directly to force MinBTL FAIL verdict."""
        tests = [
            TestOutcome(name="minbtl", verdict="FAIL", values={"min_years": 100}),
            TestOutcome(name="dsr", verdict="PASS", values={"dsr": 0.95}),
            TestOutcome(name="cpcv", verdict="PASS", values={"mean_sharpe": 0.8}),
            TestOutcome(name="bootstrap", verdict="PASS", values={"sharpe_mean": 0.7}),
        ]
        assert _overall_verdict(tests) == "FAIL"

    def test_dsr_fail_rule_via_direct_construction(self):
        """DSR FAIL -> overall FAIL."""
        tests = [
            TestOutcome(name="dsr", verdict="FAIL", values={"dsr": 0.2}),
            TestOutcome(name="minbtl", verdict="PASS", values={"min_years": 2}),
            TestOutcome(name="cpcv", verdict="PASS", values={"mean_sharpe": 0.8}),
            TestOutcome(name="bootstrap", verdict="PASS", values={"sharpe_mean": 0.7}),
        ]
        assert _overall_verdict(tests) == "FAIL"

    def test_cpcv_fail_rule_via_direct_construction(self):
        """CPCV FAIL -> overall FAIL."""
        tests = [
            TestOutcome(name="cpcv", verdict="FAIL", values={"pct5_sharpe": -1.0}),
            TestOutcome(name="dsr", verdict="PASS", values={"dsr": 0.95}),
            TestOutcome(name="minbtl", verdict="PASS", values={"min_years": 2}),
            TestOutcome(name="bootstrap", verdict="PASS", values={"sharpe_mean": 0.7}),
        ]
        assert _overall_verdict(tests) == "FAIL"

    def test_bootstrap_warn_rule_via_direct_construction(self):
        """Bootstrap WARN + rest PASS -> overall WARN."""
        tests = [
            TestOutcome(
                name="bootstrap",
                verdict="WARN",
                values={"sharpe_pct5": -0.1},
                note="fast mode",
            ),
            TestOutcome(name="dsr", verdict="PASS", values={"dsr": 0.95}),
            TestOutcome(name="minbtl", verdict="PASS", values={"min_years": 2}),
            TestOutcome(name="cpcv", verdict="PASS", values={"mean_sharpe": 0.8}),
        ]
        assert _overall_verdict(tests) == "WARN"

    def test_dsr_skip_rule_via_direct_construction(self):
        """DSR SKIP (non-MinBTL) + rest PASS -> overall WARN."""
        tests = [
            TestOutcome(name="dsr", verdict="SKIP", note="too few obs"),
            TestOutcome(name="minbtl", verdict="PASS", values={"min_years": 2}),
            TestOutcome(name="cpcv", verdict="PASS", values={"mean_sharpe": 0.8}),
            TestOutcome(name="bootstrap", verdict="PASS", values={"sharpe_mean": 0.7}),
        ]
        assert _overall_verdict(tests) == "WARN"


# ---------------------------------------------------------------------------
# Edge cases and stress tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_generated_date_format(self, synthetic_strategy, tmp_path):
        """generated field is a valid ISO date string."""
        result = run_validation_battery(
            strategy_key="test_strategy",
            results_dir=tmp_path,
            n_trials=5,
            cpcv_folds=4,
            bootstrap_n=50,
        )
        # Should be YYYY-MM-DD format
        parts = result.generated.split("-")
        assert len(parts) == 3
        assert len(parts[0]) == 4  # year
        assert len(parts[1]) == 2  # month
        assert len(parts[2]) == 2  # day

    def test_test_outcome_with_empty_values(self):
        """TestOutcome with empty values dict serializes safely."""
        outcome = TestOutcome(name="test", verdict="PASS", values={})
        d = outcome.to_dict()
        json_str = json.dumps(d)
        assert "test" in json_str

    def test_validation_result_with_empty_tests(self):
        """ValidationResult with empty tests list serializes safely."""
        result = ValidationResult(
            strategy_key="test",
            generated="2026-01-15",
            tests=[],
            overall="PASS",
        )
        json_str = json.dumps(result.to_dict())
        assert "test" in json_str

    def test_large_values_in_outcome(self):
        """TestOutcome with very large/small numbers sanitizes correctly."""
        outcome = TestOutcome(
            name="test",
            verdict="PASS",
            values={"large": 1e10, "small": 1e-10, "huge_neg": -1e20},
        )
        d = outcome.to_dict()
        json_str = json.dumps(d)
        assert "Infinity" not in json_str
        assert "NaN" not in json_str

    def test_strategy_key_with_special_chars(self, tmp_path):
        """Strategy key with underscores/hyphens handled correctly."""
        _write_synthetic_portfolio(tmp_path, "my_test-strat_123", n_months=84)
        result = run_validation_battery(
            strategy_key="my_test-strat_123",
            results_dir=tmp_path,
            n_trials=5,
            cpcv_folds=4,
            bootstrap_n=50,
        )
        assert result.strategy_key == "my_test-strat_123"


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_full_battery_produces_coherent_result(self, synthetic_strategy, tmp_path):
        """End-to-end: battery runs, all tests complete, verdicts are coherent."""
        result = run_validation_battery(
            strategy_key="test_strategy",
            results_dir=tmp_path,
            n_trials=5,
            cpcv_folds=4,
            bootstrap_n=50,
        )

        # All fields present and valid
        assert result.strategy_key == "test_strategy"
        assert isinstance(result.generated, str)
        assert len(result.tests) == 4
        assert result.overall in ("PASS", "WARN", "FAIL")

        # All tests have required fields
        for test in result.tests:
            assert test.name in ("dsr", "minbtl", "cpcv", "bootstrap")
            assert test.verdict in ("PASS", "WARN", "FAIL", "SKIP")
            assert isinstance(test.values, dict)
            assert isinstance(test.note, str)

        # Overall verdict follows the rules
        expected_overall = _overall_verdict(result.tests)
        assert result.overall == expected_overall

    def test_roundtrip_through_json(self, synthetic_strategy, tmp_path):
        """to_dict() -> json.dumps() -> json.loads() -> ValidationResult rebuilds."""
        result = run_validation_battery(
            strategy_key="test_strategy",
            results_dir=tmp_path,
            n_trials=5,
            cpcv_folds=4,
            bootstrap_n=50,
        )
        d = result.to_dict()
        json_str = json.dumps(d)
        loaded = json.loads(json_str)

        # Verify structure survives roundtrip
        assert loaded["strategy_key"] == result.strategy_key
        assert loaded["overall"] == result.overall
        assert len(loaded["tests"]) == len(result.tests)
