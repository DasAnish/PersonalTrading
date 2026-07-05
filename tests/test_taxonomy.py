"""
Tests for strategies/taxonomy.py and scripts/tag_mechanisms.py.

Covers:
1. infer_mechanism for all allocation classes, composed, and portfolio types
2. infer_overlay_mechanism for composed definitions
3. Error handling (asset, unknown type/class)
4. Tagging idempotency and stale tag replacement
5. mechanism_coverage with valid and invalid JSON files
"""

import json
import sys
from pathlib import Path

import pytest

from strategies.taxonomy import (
    MECHANISMS,
    infer_mechanism,
    infer_overlay_mechanism,
    mechanism_coverage,
)

# ============================================================================
# Fixtures and helpers
# ============================================================================


def _copy_definition(src_path, dest_path):
    """Copy a definition file from src to dest, preserving directory structure."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(src_path, "r", encoding="utf-8") as f:
        definition = json.load(f)
    with open(dest_path, "w", encoding="utf-8") as f:
        json.dump(definition, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _write_definition(path, definition):
    """Write a definition dict to a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(definition, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _read_definition(path):
    """Read a definition file back as a dict."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# Import the tagging function from the script
# Mimic the pattern from existing tests (e.g., test_results_io.py)
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from tag_mechanisms import _pending_tags, run_tagging

# ============================================================================
# Test infer_mechanism: allocation classes
# ============================================================================


class TestInferMechanismAllocations:
    """Test infer_mechanism for every allocation class in the mapping."""

    def test_hrp_strategy(self):
        """HRPStrategy -> diversification."""
        definition = {
            "type": "allocation",
            "class": "HRPStrategy",
            "parameters": {"linkage_method": "ward"},
        }
        assert infer_mechanism(definition) == "diversification"

    def test_equal_weight_strategy(self):
        """EqualWeightStrategy -> diversification."""
        definition = {"type": "allocation", "class": "EqualWeightStrategy"}
        assert infer_mechanism(definition) == "diversification"

    def test_minimum_variance_strategy(self):
        """MinimumVarianceStrategy -> diversification."""
        definition = {"type": "allocation", "class": "MinimumVarianceStrategy"}
        assert infer_mechanism(definition) == "diversification"

    def test_risk_parity_strategy(self):
        """RiskParityStrategy -> diversification."""
        definition = {"type": "allocation", "class": "RiskParityStrategy"}
        assert infer_mechanism(definition) == "diversification"

    def test_trend_following_strategy(self):
        """TrendFollowingStrategy -> trend."""
        definition = {"type": "allocation", "class": "TrendFollowingStrategy"}
        assert infer_mechanism(definition) == "trend"

    def test_trend_signal_mvo_strategy(self):
        """TrendSignalMVOStrategy -> trend."""
        definition = {"type": "allocation", "class": "TrendSignalMVOStrategy"}
        assert infer_mechanism(definition) == "trend"

    def test_trend_signal_rp_strategy(self):
        """TrendSignalRPStrategy -> trend."""
        definition = {"type": "allocation", "class": "TrendSignalRPStrategy"}
        assert infer_mechanism(definition) == "trend"

    def test_dual_momentum_strategy(self):
        """DualMomentumStrategy -> trend."""
        definition = {"type": "allocation", "class": "DualMomentumStrategy"}
        assert infer_mechanism(definition) == "trend"

    def test_momentum_topn_strategy(self):
        """MomentumTopNStrategy -> momentum-cs."""
        definition = {"type": "allocation", "class": "MomentumTopNStrategy"}
        assert infer_mechanism(definition) == "momentum-cs"

    def test_volatility_momentum_strategy(self):
        """VolatilityMomentumStrategy -> momentum-cs."""
        definition = {"type": "allocation", "class": "VolatilityMomentumStrategy"}
        assert infer_mechanism(definition) == "momentum-cs"

    def test_mean_reversion_strategy(self):
        """MeanReversionStrategy -> mean-reversion."""
        definition = {"type": "allocation", "class": "MeanReversionStrategy"}
        assert infer_mechanism(definition) == "mean-reversion"

    def test_skewness_weighted_strategy(self):
        """SkewnessWeightedStrategy -> vol-premium."""
        definition = {"type": "allocation", "class": "SkewnessWeightedStrategy"}
        assert infer_mechanism(definition) == "vol-premium"

    def test_adaptive_asset_allocation_strategy(self):
        """AdaptiveAssetAllocationStrategy -> regime."""
        definition = {"type": "allocation", "class": "AdaptiveAssetAllocationStrategy"}
        assert infer_mechanism(definition) == "regime"

    def test_protective_asset_allocation_strategy(self):
        """ProtectiveAssetAllocationStrategy -> regime."""
        definition = {
            "type": "allocation",
            "class": "ProtectiveAssetAllocationStrategy",
        }
        assert infer_mechanism(definition) == "regime"

    def test_meta_portfolio_strategy(self):
        """MetaPortfolioStrategy (via allocation) -> meta."""
        definition = {"type": "allocation", "class": "MetaPortfolioStrategy"}
        assert infer_mechanism(definition) == "meta"


# ============================================================================
# Test infer_mechanism: composed and portfolio
# ============================================================================


class TestInferMechanismComposed:
    """Test that composed definitions return their underlying's mechanism."""

    def test_composed_vol_target_over_hrp(self):
        """Composed (VolatilityTargetStrategy) over HRP -> underlying's mechanism."""
        definition = {
            "type": "composed",
            "class": "VolatilityTargetStrategy",
            "parameters": {"target_vol": 0.15},
            "underlying": {
                "type": "allocation",
                "class": "HRPStrategy",
                "parameters": {"linkage_method": "ward"},
            },
        }
        assert infer_mechanism(definition) == "diversification"

    def test_composed_constraint_over_trend(self):
        """Composed (ConstraintStrategy) over TrendFollowingStrategy."""
        definition = {
            "type": "composed",
            "class": "ConstraintStrategy",
            "parameters": {},
            "underlying": {
                "type": "allocation",
                "class": "TrendFollowingStrategy",
            },
        }
        assert infer_mechanism(definition) == "trend"

    def test_composed_leverage_over_momentum(self):
        """Composed (LeverageStrategy) over MomentumTopNStrategy."""
        definition = {
            "type": "composed",
            "class": "LeverageStrategy",
            "parameters": {"leverage": 1.5},
            "underlying": {
                "type": "allocation",
                "class": "MomentumTopNStrategy",
            },
        }
        assert infer_mechanism(definition) == "momentum-cs"


class TestInferMechanismPortfolio:
    """Test that portfolio definitions always return 'meta'."""

    def test_portfolio_always_meta(self):
        """type: portfolio -> 'meta'."""
        definition = {
            "type": "portfolio",
            "class": "MetaPortfolioStrategy",
            "parameters": {},
        }
        assert infer_mechanism(definition) == "meta"

    def test_portfolio_with_underlying(self):
        """Portfolio with underlying still returns 'meta'."""
        definition = {
            "type": "portfolio",
            "class": "MetaPortfolioStrategy",
            "underlying": ["composed/trend_15vol", "composed/hrp_15vol"],
        }
        assert infer_mechanism(definition) == "meta"


# ============================================================================
# Test infer_mechanism: error handling
# ============================================================================


class TestInferMechanismErrors:
    """Test error cases for infer_mechanism."""

    def test_asset_raises_value_error(self):
        """type: asset raises ValueError."""
        definition = {"type": "asset", "symbol": "VUSA"}
        with pytest.raises(ValueError, match="Assets are not strategies"):
            infer_mechanism(definition)

    def test_unknown_definition_type(self):
        """Unknown type raises ValueError mentioning the type."""
        definition = {"type": "unknown_type"}
        with pytest.raises(ValueError, match="Unknown definition type"):
            infer_mechanism(definition)

    def test_allocation_unknown_class(self):
        """Allocation with unknown class raises ValueError mentioning class."""
        definition = {"type": "allocation", "class": "UnknownStrategy"}
        with pytest.raises(
            ValueError, match="Unknown allocation class.*UnknownStrategy"
        ):
            infer_mechanism(definition)

    def test_allocation_missing_class(self):
        """Allocation without class field raises ValueError."""
        definition = {"type": "allocation"}
        with pytest.raises(ValueError, match="Unknown allocation class"):
            infer_mechanism(definition)


# ============================================================================
# Test infer_overlay_mechanism
# ============================================================================


class TestInferOverlayMechanism:
    """Test infer_overlay_mechanism for composed definitions."""

    def test_volatility_target_is_hedging_overlay(self):
        """VolatilityTargetStrategy -> hedging-overlay."""
        definition = {"type": "composed", "class": "VolatilityTargetStrategy"}
        assert infer_overlay_mechanism(definition) == "hedging-overlay"

    def test_constraint_is_hedging_overlay(self):
        """ConstraintStrategy -> hedging-overlay."""
        definition = {"type": "composed", "class": "ConstraintStrategy"}
        assert infer_overlay_mechanism(definition) == "hedging-overlay"

    def test_leverage_is_hedging_overlay(self):
        """LeverageStrategy -> hedging-overlay."""
        definition = {"type": "composed", "class": "LeverageStrategy"}
        assert infer_overlay_mechanism(definition) == "hedging-overlay"

    def test_non_composed_returns_none(self):
        """Non-composed definition returns None."""
        definition = {"type": "allocation", "class": "HRPStrategy"}
        assert infer_overlay_mechanism(definition) is None

    def test_portfolio_returns_none(self):
        """Portfolio definition returns None."""
        definition = {"type": "portfolio", "class": "MetaPortfolioStrategy"}
        assert infer_overlay_mechanism(definition) is None

    def test_asset_returns_none(self):
        """Asset definition returns None (not an overlay)."""
        definition = {"type": "asset", "symbol": "VUSA"}
        assert infer_overlay_mechanism(definition) is None

    def test_unknown_overlay_class_raises(self):
        """Unknown overlay class raises ValueError."""
        definition = {"type": "composed", "class": "UnknownOverlay"}
        with pytest.raises(ValueError, match="Unknown overlay class.*UnknownOverlay"):
            infer_overlay_mechanism(definition)


# ============================================================================
# Test tagging idempotency
# ============================================================================


class TestTaggingIdempotency:
    """Test that running tagging twice produces no changes on second run."""

    def test_tagging_idempotent_with_real_definitions(self, tmp_path):
        """Copy real definitions, tag twice, second pass reports zero changes."""
        # Copy a few real definition files
        repo_path = Path(__file__).parent.parent
        src_allocation = (
            repo_path / "strategy_definitions" / "allocations" / "hrp_single.json"
        )
        src_composed = (
            repo_path / "strategy_definitions" / "composed" / "hrp_15vol.json"
        )
        src_portfolio = (
            repo_path
            / "strategy_definitions"
            / "portfolios"
            / "meta_trend_hrp_15vol.json"
        )

        # Create the mirrored structure in tmp_path
        _copy_definition(src_allocation, tmp_path / "allocations" / "hrp_single.json")
        _copy_definition(src_composed, tmp_path / "composed" / "hrp_15vol.json")
        _copy_definition(
            src_portfolio, tmp_path / "portfolios" / "meta_trend_hrp_15vol.json"
        )

        # First pass: run tagging
        run_tagging(tmp_path, dry_run=False)

        # Read files after first pass
        alloc_after_1 = _read_definition(tmp_path / "allocations" / "hrp_single.json")
        comp_after_1 = _read_definition(tmp_path / "composed" / "hrp_15vol.json")
        port_after_1 = _read_definition(
            tmp_path / "portfolios" / "meta_trend_hrp_15vol.json"
        )

        # Second pass: run tagging again
        run_tagging(tmp_path, dry_run=False)

        # Read files after second pass
        alloc_after_2 = _read_definition(tmp_path / "allocations" / "hrp_single.json")
        comp_after_2 = _read_definition(tmp_path / "composed" / "hrp_15vol.json")
        port_after_2 = _read_definition(
            tmp_path / "portfolios" / "meta_trend_hrp_15vol.json"
        )

        # Second pass should produce identical files (no changes)
        assert alloc_after_1 == alloc_after_2
        assert comp_after_1 == comp_after_2
        assert port_after_1 == port_after_2

    def test_tagging_only_changes_tags_array(self, tmp_path):
        """Only the tags array should change; all other keys should be identical."""
        repo_path = Path(__file__).parent.parent
        src = repo_path / "strategy_definitions" / "allocations" / "equal_weight.json"

        # Copy and read original
        dest = tmp_path / "allocations" / "equal_weight.json"
        _copy_definition(src, dest)

        with open(dest, "r", encoding="utf-8") as f:
            original = json.load(f)

        # Remove tags to start fresh
        original_no_tags = {k: v for k, v in original.items() if k != "tags"}

        # Write back without tags
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(original_no_tags, f, indent=2, ensure_ascii=False)
            f.write("\n")

        # Run tagging
        run_tagging(tmp_path, dry_run=False)

        # Read result
        with open(dest, "r", encoding="utf-8") as f:
            tagged = json.load(f)

        # All keys except tags should match original_no_tags
        tagged_no_tags = {k: v for k, v in tagged.items() if k != "tags"}
        assert tagged_no_tags == original_no_tags

        # tags should be present and contain the correct mechanism
        assert "tags" in tagged
        assert any(t.startswith("mech:") for t in tagged["tags"])


# ============================================================================
# Test stale tag replacement
# ============================================================================


class TestStaleTagReplacement:
    """Test that stale mech:* tags are replaced, other tags preserved."""

    def test_replaces_old_mech_tag_preserves_others(self, tmp_path):
        """File with ['mech:wrong', 'foo'] becomes ['foo', 'mech:correct']."""
        definition = {
            "type": "allocation",
            "class": "HRPStrategy",
            "tags": ["mech:wrong-tag", "foo"],
        }
        dest = tmp_path / "allocations" / "test.json"
        _write_definition(dest, definition)

        # Run tagging
        run_tagging(tmp_path, dry_run=False)

        # Read result
        result = _read_definition(dest)
        tags = result["tags"]

        # Should have exactly one mech:* tag (the correct one)
        mech_tags = [t for t in tags if isinstance(t, str) and t.startswith("mech:")]
        assert len(mech_tags) == 1
        assert mech_tags[0] == "mech:diversification"

        # "foo" should be preserved
        assert "foo" in tags

    def test_pending_tags_helper_logic(self):
        """Test _pending_tags helper directly."""
        old_definition = {
            "type": "allocation",
            "class": "HRPStrategy",
            "tags": ["old-tag", "mech:old-mechanism"],
        }

        new_tags, changed = _pending_tags(old_definition, "diversification")

        # Should have old-tag and new mech tag
        assert "old-tag" in new_tags
        assert "mech:diversification" in new_tags
        # Should not have old mech tag
        assert "mech:old-mechanism" not in new_tags
        # Should report change because old mech tag was different
        assert changed


# ============================================================================
# Test mechanism_coverage
# ============================================================================


class TestMechanismCoverage:
    """Test mechanism_coverage function."""

    def test_mechanism_coverage_counts_correctly(self, tmp_path):
        """mechanism_coverage returns correct counts per mechanism."""
        repo_path = Path(__file__).parent.parent
        src_alloc1 = (
            repo_path / "strategy_definitions" / "allocations" / "hrp_single.json"
        )
        src_alloc2 = (
            repo_path / "strategy_definitions" / "allocations" / "equal_weight.json"
        )
        src_trend = (
            repo_path / "strategy_definitions" / "allocations" / "trend_following.json"
        )

        _copy_definition(src_alloc1, tmp_path / "allocations" / "hrp1.json")
        _copy_definition(src_alloc2, tmp_path / "allocations" / "equal.json")
        _copy_definition(src_trend, tmp_path / "allocations" / "trend.json")

        counts = mechanism_coverage(tmp_path)

        assert counts["diversification"] == 2
        assert counts["trend"] == 1

    def test_mechanism_coverage_skips_invalid_json(self, tmp_path, caplog):
        """mechanism_coverage skips invalid JSON files with warning."""
        repo_path = Path(__file__).parent.parent
        src = repo_path / "strategy_definitions" / "allocations" / "hrp_single.json"
        _copy_definition(src, tmp_path / "allocations" / "valid.json")

        # Create an invalid JSON file
        (tmp_path / "allocations").mkdir(parents=True, exist_ok=True)
        invalid_path = tmp_path / "allocations" / "invalid.json"
        invalid_path.write_text("{invalid json content")

        # Run coverage (should not raise)
        counts = mechanism_coverage(tmp_path)

        # Should count the valid file
        assert counts["diversification"] == 1
        # Should have skipped the invalid file (logged warning)
        assert any("invalid.json" in record.message for record in caplog.records)

    def test_mechanism_coverage_all_mechanisms_possible(self, tmp_path):
        """mechanism_coverage can return any mechanism from MECHANISMS."""
        # Build a minimal definition for each mechanism
        mechanisms_to_test = [
            ("trend", {"type": "allocation", "class": "TrendFollowingStrategy"}),
            ("momentum-cs", {"type": "allocation", "class": "MomentumTopNStrategy"}),
            (
                "mean-reversion",
                {"type": "allocation", "class": "MeanReversionStrategy"},
            ),
            ("diversification", {"type": "allocation", "class": "HRPStrategy"}),
            (
                "vol-premium",
                {"type": "allocation", "class": "SkewnessWeightedStrategy"},
            ),
            (
                "regime",
                {"type": "allocation", "class": "AdaptiveAssetAllocationStrategy"},
            ),
            ("meta", {"type": "portfolio", "class": "MetaPortfolioStrategy"}),
        ]

        for idx, (expected_mech, defn) in enumerate(mechanisms_to_test):
            dest = tmp_path / "allocations" / f"test_{idx}.json"
            _write_definition(dest, defn)

        counts = mechanism_coverage(tmp_path)

        # Check that we got counts for expected mechanisms
        for expected_mech, _ in mechanisms_to_test:
            assert expected_mech in counts
            assert counts[expected_mech] >= 1


# ============================================================================
# Test MECHANISMS tuple is complete and valid
# ============================================================================


def test_mechanisms_tuple_is_valid():
    """MECHANISMS tuple contains valid mechanism names."""
    assert isinstance(MECHANISMS, tuple)
    assert len(MECHANISMS) > 0
    assert all(isinstance(m, str) for m in MECHANISMS)
    # Check a few expected mechanisms
    assert "diversification" in MECHANISMS
    assert "trend" in MECHANISMS
    assert "meta" in MECHANISMS
    assert "hedging-overlay" in MECHANISMS
