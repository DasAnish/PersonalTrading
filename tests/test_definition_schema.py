"""
Tests for strategy definition schema validation.

Tests the pydantic schema for strategy definitions, ensuring all real files
pass validation and that schema constraints are enforced.
"""

import pytest
import json
from pathlib import Path
from strategies.definition_schema import StrategyDefinition, validate_definition


class TestStrategyDefinitionSchema:
    """Test the StrategyDefinition pydantic model."""

    def test_minimal_valid_definition(self):
        """Test that minimal valid definition is accepted."""
        data = {"class": "SomeStrategy"}
        definition = StrategyDefinition(**data)
        assert definition.class_ == "SomeStrategy"

    def test_full_valid_definition(self):
        """Test that full valid definition is accepted."""
        data = {
            "class": "EqualWeightStrategy",
            "type": "allocation",
            "name": "Equal Weight",
            "description": "Equal weight across all assets",
            "parameters": {"target_vol": 0.15},
            "underlying": "universe:all",
            "tags": ["momentum", "risk-parity"],
        }
        definition = StrategyDefinition(**data)
        assert definition.class_ == "EqualWeightStrategy"
        assert definition.type == "allocation"
        assert definition.name == "Equal Weight"

    def test_missing_class_raises(self):
        """Test that missing 'class' field raises validation error."""
        data = {"type": "allocation"}
        with pytest.raises(ValueError):
            StrategyDefinition(**data)

    def test_empty_class_raises(self):
        """Test that empty 'class' string raises validation error."""
        data = {"class": ""}
        with pytest.raises(ValueError):
            StrategyDefinition(**data)

    def test_class_alias(self):
        """Test that 'class' field is aliased correctly."""
        data = {"class": "MyStrategy"}
        definition = StrategyDefinition(**data)
        assert definition.class_ == "MyStrategy"

    def test_optional_fields_none(self):
        """Test that optional fields can be None."""
        data = {"class": "Strategy"}
        definition = StrategyDefinition(**data)
        assert definition.name is None
        assert definition.description is None
        assert definition.parameters is None

    def test_parameters_with_negative_numeric_allowed(self):
        """Test that negative numeric parameters are allowed."""
        data = {
            "class": "Strategy",
            "parameters": {"drawdown_trigger": -0.15},
        }
        definition = StrategyDefinition(**data)
        assert definition.parameters["drawdown_trigger"] == -0.15

    def test_parameters_with_zero_numeric_ok(self):
        """Test that zero numeric parameters are allowed."""
        data = {
            "class": "Strategy",
            "parameters": {"threshold": 0.0},
        }
        definition = StrategyDefinition(**data)
        assert definition.parameters["threshold"] == 0.0

    def test_extra_fields_allowed(self):
        """Test that extra fields are allowed via extra='allow'."""
        data = {
            "class": "Strategy",
            "custom_field": "custom_value",
            "another_custom": 123,
        }
        definition = StrategyDefinition(**data)
        assert definition.class_ == "Strategy"
        # Extra fields are stored in __pydantic_extra__ with Pydantic v2
        assert hasattr(definition, "__pydantic_extra__")

    def test_underlying_as_string(self):
        """Test that underlying can be a string reference."""
        data = {
            "class": "Strategy",
            "underlying": "universe:all",
        }
        definition = StrategyDefinition(**data)
        assert definition.underlying == "universe:all"

    def test_underlying_as_list(self):
        """Test that underlying can be a list of references."""
        data = {
            "class": "Strategy",
            "underlying": ["allocation/equal_weight", "assets/vusa"],
        }
        definition = StrategyDefinition(**data)
        assert isinstance(definition.underlying, list)

    def test_underlying_as_dict(self):
        """Test that underlying can be an inline definition dict."""
        data = {
            "class": "Strategy",
            "underlying": {
                "type": "allocation",
                "class": "InlineStrategy",
            },
        }
        definition = StrategyDefinition(**data)
        assert isinstance(definition.underlying, dict)


class TestValidateDefinitionFunction:
    """Test the validate_definition helper function."""

    def test_validate_definition_success(self):
        """Test successful validation via validate_definition."""
        data = {"class": "TestStrategy", "type": "allocation"}
        result = validate_definition(data, "test.json")
        assert result.class_ == "TestStrategy"

    def test_validate_definition_missing_class_raises(self):
        """Test that validate_definition raises on missing class."""
        data = {"type": "allocation"}
        with pytest.raises(ValueError) as exc_info:
            validate_definition(data, "test.json")
        assert "test.json" in str(exc_info.value)

    def test_validate_definition_error_includes_source(self):
        """Test that error messages include the source file path."""
        data = {"class": ""}
        with pytest.raises(ValueError) as exc_info:
            validate_definition(data, "/path/to/test.json")
        assert "/path/to/test.json" in str(exc_info.value)


class TestRealDefinitionFiles:
    """Test real strategy definition files from the repo."""

    @pytest.fixture
    def definitions_dir(self) -> Path:
        """Get path to strategy_definitions directory."""
        return Path(__file__).parent.parent / "strategy_definitions"

    def test_all_json_definitions_pass_validation(self, definitions_dir):
        """Test that all real JSON definition files pass validation."""
        # Only look in strategy subdirectories
        strategy_dirs = [
            "allocations",
            "composed",
            "overlays",
            "portfolios",
            "assets",
        ]
        json_files = []
        for subdir in strategy_dirs:
            subdir_path = definitions_dir / subdir
            if subdir_path.exists():
                json_files.extend(subdir_path.glob("*.json"))

        failures = []
        for file_path in json_files:
            try:
                with open(file_path, "r") as f:
                    data = json.load(f)
                validate_definition(data, str(file_path))
            except Exception as e:
                failures.append((file_path, str(e)))

        if failures:
            error_msg = "\n".join([f"  {f}: {e}" for f, e in failures[:10]])
            if len(failures) > 10:
                error_msg += f"\n  ... and {len(failures) - 10} more"
            pytest.fail(f"Failed to validate {len(failures)} files:\n{error_msg}")

    def test_equal_weight_definition_valid(self, definitions_dir):
        """Test that equal_weight strategy definition is valid."""
        file_path = definitions_dir / "allocations" / "equal_weight.json"
        if file_path.exists():
            with open(file_path, "r") as f:
                data = json.load(f)
            definition = validate_definition(data, str(file_path))
            assert definition.class_ == "EqualWeightStrategy"
            assert definition.type == "allocation"

    def test_real_composed_definition_valid(self, definitions_dir):
        """Test that a real composed strategy definition is valid."""
        file_path = definitions_dir / "composed" / "aaa_full_universe_15vol.json"
        if file_path.exists():
            with open(file_path, "r") as f:
                data = json.load(f)
            definition = validate_definition(data, str(file_path))
            assert definition.class_ == "VolatilityTargetStrategy"
            assert definition.type == "composed"
            assert definition.parameters is not None
            assert "target_vol" in definition.parameters
