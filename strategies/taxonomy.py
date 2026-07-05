"""
Economic-mechanism taxonomy for strategy definitions.

Every strategy definition (allocation / composed / portfolio) is mapped to a
single economic mechanism from a fixed vocabulary. This lets the strategist
steer toward underrepresented mechanisms instead of re-mining the same
allocation classes.

Definition shapes (see ``strategy_definitions/``):
    - ``type: asset``       — a raw instrument; not a strategy, raises.
    - ``type: allocation``  — mechanism is derived from ``class``.
    - ``type: composed``    — an overlay (vol-target/constraint/leverage)
      wrapped around an ``underlying`` definition (embedded dict, not a file
      reference); mechanism is the mechanism of that ``underlying``.
    - ``type: portfolio``   — a blend of other strategies; always ``meta``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MECHANISMS: tuple[str, ...] = (
    "trend",
    "momentum-cs",
    "mean-reversion",
    "carry",
    "vol-premium",
    "diversification",
    "regime",
    "hedging-overlay",
    "seasonality",
    "meta",
)

# type: allocation -> mechanism, keyed by "class".
_ALLOCATION_CLASS_TO_MECHANISM: dict[str, str] = {
    "HRPStrategy": "diversification",
    "EqualWeightStrategy": "diversification",
    "MinimumVarianceStrategy": "diversification",
    "RiskParityStrategy": "diversification",
    "TrendFollowingStrategy": "trend",
    "TrendSignalMVOStrategy": "trend",
    "TrendSignalRPStrategy": "trend",
    # Dual Momentum applies an absolute-momentum (trend) filter on top of its
    # relative-momentum ranking; the absolute filter is what keeps it out of
    # downtrending assets entirely, so it is classified as trend rather than
    # momentum-cs.
    "DualMomentumStrategy": "trend",
    "MomentumTopNStrategy": "momentum-cs",
    "VolatilityMomentumStrategy": "momentum-cs",
    "MeanReversionStrategy": "mean-reversion",
    "SkewnessWeightedStrategy": "vol-premium",
    "AdaptiveAssetAllocationStrategy": "regime",
    "ProtectiveAssetAllocationStrategy": "regime",
    "MetaPortfolioStrategy": "meta",
}

# type: composed -> the overlay's own mechanism, keyed by the composed
# definition's "class" (the overlay class, not the wrapped underlying).
_OVERLAY_CLASS_TO_MECHANISM: dict[str, str] = {
    "VolatilityTargetStrategy": "hedging-overlay",
    "ConstraintStrategy": "hedging-overlay",
    "LeverageStrategy": "hedging-overlay",
}

DEFINITION_SUBDIRS: tuple[str, ...] = ("allocations", "composed", "portfolios")


def infer_mechanism(definition: dict) -> str:
    """Map a strategy-definition dict to its economic mechanism.

    Args:
        definition: A parsed strategy-definition JSON (or an embedded
            ``underlying`` sub-dict of one).

    Returns:
        One of the values in ``MECHANISMS``.

    Raises:
        ValueError: If ``definition`` is an asset, has an unrecognized
            ``type``, or has an unrecognized ``class`` for its type.
    """
    def_type = definition.get("type")

    if def_type == "asset":
        raise ValueError("Assets are not strategies and have no mechanism.")

    if def_type == "portfolio":
        return "meta"

    if def_type == "composed":
        return infer_mechanism(definition["underlying"])

    if def_type == "allocation":
        class_name = definition.get("class")
        if class_name not in _ALLOCATION_CLASS_TO_MECHANISM:
            raise ValueError(f"Unknown allocation class: {class_name!r}")
        return _ALLOCATION_CLASS_TO_MECHANISM[class_name]

    raise ValueError(f"Unknown definition type: {def_type!r}")


def infer_overlay_mechanism(definition: dict) -> str | None:
    """Return the mechanism of the overlay wrapping a ``composed`` definition.

    Returns ``None`` for non-``composed`` definitions (there is no overlay).

    Raises:
        ValueError: If the definition is ``composed`` but its ``class`` is
            not a recognized overlay class.
    """
    if definition.get("type") != "composed":
        return None

    class_name = definition.get("class")
    if class_name not in _OVERLAY_CLASS_TO_MECHANISM:
        raise ValueError(f"Unknown overlay class: {class_name!r}")
    return _OVERLAY_CLASS_TO_MECHANISM[class_name]


def mechanism_coverage(definitions_dir: Path) -> dict[str, int]:
    """Count strategy definitions per mechanism.

    Walks ``allocations/``, ``composed/``, and ``portfolios/`` under
    ``definitions_dir`` (assets are not strategies and are skipped). Files
    that fail to parse as JSON are skipped with a warning.

    Args:
        definitions_dir: Path to the ``strategy_definitions`` directory.

    Returns:
        Mapping of mechanism -> count.
    """
    counts: dict[str, int] = {}

    for subdir in DEFINITION_SUBDIRS:
        for path in sorted((definitions_dir / subdir).glob("*.json")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    definition = json.load(f)
            except json.JSONDecodeError as exc:
                logger.warning("Skipping %s: invalid JSON (%s)", path, exc)
                continue

            mechanism = infer_mechanism(definition)
            counts[mechanism] = counts.get(mechanism, 0) + 1

    return counts
