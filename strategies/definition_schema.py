"""
Pydantic schema for strategy definitions.

Validates JSON strategy definition files against a common schema.
Supports flexible parameters and nested underlying references.
"""

from __future__ import annotations
from typing import Optional, Dict, Any, List, Union
from pydantic import BaseModel, Field, ConfigDict, field_validator


class StrategyDefinition(BaseModel):
    """
    Schema for strategy definition files.

    All strategy JSON files must have:
    - type: allocation, composed, overlay, portfolio, asset, or market
    - class: non-empty string naming the strategy class

    Optional fields:
    - name: human-readable name
    - description: detailed description
    - parameters: dict of strategy-specific configuration
    - underlying: reference(s) to underlying strategies
    - tags: list of categorization tags

    Extra fields are allowed to support future extensions.
    """

    model_config = ConfigDict(extra="allow")

    class_: str = Field(alias="class")
    type: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    underlying: Optional[
        Union[str, List[Union[str, Dict[str, Any]]], Dict[str, Any]]
    ] = None
    tags: Optional[List[str]] = None

    @field_validator("class_")
    @classmethod
    def class_must_not_be_empty(cls, v: str) -> str:
        """Ensure class field is a non-empty string."""
        if not v or not isinstance(v, str):
            raise ValueError("'class' must be a non-empty string")
        return v

    @field_validator("parameters", mode="before")
    @classmethod
    def validate_parameters(cls, v: Any) -> Optional[Dict[str, Any]]:
        """Validate parameters dict if present."""
        if v is None:
            return None
        if not isinstance(v, dict):
            raise ValueError("'parameters' must be a dict")
        return v


def validate_definition(data: Dict[str, Any], source: str) -> StrategyDefinition:
    """
    Validate a strategy definition dict against the schema.

    Args:
        data: Dictionary from JSON file
        source: File path for error reporting

    Returns:
        Validated StrategyDefinition

    Raises:
        ValueError: If validation fails
    """
    try:
        return StrategyDefinition(**data)
    except Exception as e:
        raise ValueError(f"Invalid strategy definition in {source}: {e}") from e
