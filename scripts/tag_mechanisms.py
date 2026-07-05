"""
Tag every strategy definition with its economic mechanism (``mech:<tag>``)
and, optionally, report mechanism coverage.

Walks ``strategy_definitions/{allocations,composed,portfolios}/*.json``,
infers each definition's mechanism via ``strategies.taxonomy.infer_mechanism``,
and ensures a matching ``mech:<tag>`` entry is present in the file's ``tags``
array (creating ``tags`` if absent, replacing any stale ``mech:*`` tag).
Idempotent: running it twice in a row makes no further changes.

Usage:
    # Preview pending changes without writing
    python scripts/tag_mechanisms.py --dry-run

    # Apply tags in place
    python scripts/tag_mechanisms.py

    # Write results/mechanism_coverage.json (no tagging)
    python scripts/tag_mechanisms.py --coverage
"""

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from strategies.taxonomy import DEFINITION_SUBDIRS, infer_mechanism, mechanism_coverage

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEFINITIONS_DIR = Path("strategy_definitions")
RESULTS_DIR = Path("results")


def _iter_definition_files(definitions_dir: Path):
    for subdir in DEFINITION_SUBDIRS:
        for path in sorted((definitions_dir / subdir).glob("*.json")):
            yield path


def _pending_tags(definition: dict, mechanism: str) -> tuple[list, bool]:
    """Return (new_tags, changed) for ``definition`` given its mechanism."""
    old_tags = definition.get("tags", [])
    mech_tag = f"mech:{mechanism}"
    kept = [t for t in old_tags if not (isinstance(t, str) and t.startswith("mech:"))]
    new_tags = kept + [mech_tag]
    return new_tags, new_tags != old_tags


def _write_definition(path: Path, definition: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(definition, f, indent=2, ensure_ascii=False)
        f.write("\n")


def run_tagging(definitions_dir: Path, dry_run: bool) -> None:
    pending = 0
    total = 0
    mechanism_counts: dict[str, int] = {}

    for path in _iter_definition_files(definitions_dir):
        try:
            with open(path, "r", encoding="utf-8") as f:
                definition = json.load(f)
        except json.JSONDecodeError as exc:
            logger.warning("Skipping %s: invalid JSON (%s)", path, exc)
            continue

        total += 1
        mechanism = infer_mechanism(definition)
        mechanism_counts[mechanism] = mechanism_counts.get(mechanism, 0) + 1

        new_tags, changed = _pending_tags(definition, mechanism)
        if not changed:
            continue

        pending += 1
        rel_path = path.relative_to(definitions_dir)
        if dry_run:
            print(f"  {rel_path}: tags -> {new_tags}")
        else:
            definition["tags"] = new_tags
            _write_definition(path, definition)
            print(f"  TAGGED: {rel_path} -> {new_tags}")

    verb = "Would update" if dry_run else "Updated"
    print(f"\n{verb} {pending}/{total} definition(s).")
    print("\nPer-mechanism counts:")
    for mechanism, count in sorted(mechanism_counts.items()):
        print(f"  {mechanism}: {count}")


def run_coverage(definitions_dir: Path, results_dir: Path) -> None:
    counts = mechanism_coverage(definitions_dir)
    report = {
        "generated": date.today().isoformat(),
        "counts": counts,
        "total": sum(counts.values()),
    }

    results_dir.mkdir(parents=True, exist_ok=True)
    out_path = results_dir / "mechanism_coverage.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Wrote coverage for {report['total']} definition(s) to {out_path}\n")
    for mechanism, count in sorted(counts.items()):
        print(f"  {mechanism}: {count}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tag strategy definitions with their economic mechanism, "
        "or report mechanism coverage.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print pending tag changes without writing any files.",
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Write results/mechanism_coverage.json and print per-mechanism "
        "counts; does not modify any definition files.",
    )
    parser.add_argument(
        "--definitions-dir",
        type=str,
        default=str(DEFINITIONS_DIR),
        help=f"Strategy definitions directory (default: {DEFINITIONS_DIR}).",
    )
    parser.add_argument(
        "--results-dir",
        type=str,
        default=str(RESULTS_DIR),
        help=f"Directory to write coverage report into (default: {RESULTS_DIR}).",
    )

    args = parser.parse_args()
    definitions_dir = Path(args.definitions_dir)

    if args.coverage:
        run_coverage(definitions_dir, Path(args.results_dir))
        return

    run_tagging(definitions_dir, args.dry_run)


if __name__ == "__main__":
    main()
