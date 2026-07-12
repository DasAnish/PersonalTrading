#!/usr/bin/env python
"""
Validate all strategy definition files against the pydantic schema.

Scans all JSON/YAML files in strategy_definitions/ and reports pass/fail
per file. Exits with status 0 if all valid, non-zero on any failure.

Usage:
    python scripts/validate_definitions.py
"""

import sys
import json
import yaml
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from strategies.definition_schema import validate_definition  # noqa: E402


def validate_all_definitions() -> List[tuple[str, bool, str]]:
    """
    Validate all strategy definition files.

    Returns:
        List of (file_path, passed, message) tuples
    """
    config_dir = Path(__file__).parent.parent / "strategy_definitions"
    results: List[tuple[str, bool, str]] = []

    # Find all JSON and YAML files in strategy subdirectories
    strategy_dirs = [
        "allocations",
        "composed",
        "overlays",
        "portfolios",
        "assets",
    ]
    definition_files = []
    for subdir in strategy_dirs:
        definition_files.extend((config_dir / subdir).glob("*.json"))
        definition_files.extend((config_dir / subdir).glob("*.yaml"))

    for file_path in sorted(definition_files):

        try:
            # Load the file
            with open(file_path, "r") as f:
                if file_path.suffix == ".json":
                    data = json.load(f)
                else:
                    data = yaml.safe_load(f)

            # Validate against schema
            validate_definition(data, str(file_path))
            results.append((str(file_path), True, "PASS"))

        except Exception as e:
            results.append((str(file_path), False, f"FAIL: {e}"))

    return results


def main() -> int:
    """Run validation and report results."""
    results = validate_all_definitions()

    passed = sum(1 for _, p, _ in results if p)
    failed = sum(1 for _, p, _ in results if not p)

    # Print summary
    print(f"\nStrategy Definition Validation Results")
    print(f"=" * 70)

    # Print failures first
    failures = [r for r in results if not r[1]]
    if failures:
        print(f"\nFAILED ({len(failures)}):")
        for file_path, _, message in failures:
            print(f"  {file_path}")
            print(f"    {message}")

    # Print passes
    passes = [r for r in results if r[1]]
    if passes:
        print(f"\nPASSED ({len(passes)}):")
        for file_path, _, _ in passes[:5]:  # Show first 5
            print(f"  {file_path}")
        if len(passes) > 5:
            print(f"  ... and {len(passes) - 5} more")

    print(f"\n{'-' * 70}")
    print(f"Total: {passed} passed, {failed} failed out of {len(results)}")

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
