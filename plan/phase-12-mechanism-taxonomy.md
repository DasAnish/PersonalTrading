# Phase 12 — Mechanism Taxonomy + Coverage Report

**Model**: sonnet (taxonomy module) + haiku (tests, batch run)

## Goal
Tag every strategy definition with its economic mechanism so the strategist can be steered
toward underrepresented mechanisms instead of re-mining crowded ones (128/175 definitions
are recombinations of the same allocation classes).

Fixed vocabulary: `trend`, `momentum-cs`, `mean-reversion`, `carry`, `vol-premium`,
`diversification` (HRP/risk-parity/min-var/equal-weight), `regime` (adaptive/protective AA),
`hedging-overlay` (vol-target/constraint/leverage), `seasonality`, `meta` (portfolios).

## TODOs
- [x] `strategies/taxonomy.py` (<200 lines) — `MECHANISMS` constant;
      `infer_mechanism(definition: dict) -> str` mapping `class` → mechanism
      (composed = mechanism of underlying; overlay recorded separately);
      `mechanism_coverage(definitions_dir) -> dict[str, int]`
- [x] `scripts/tag_mechanisms.py` — walk `strategy_definitions/{allocations,composed,portfolios}/`,
      append `mech:<tag>` to each JSON's `tags` array (create if absent); idempotent;
      `--dry-run` prints diff counts; `--coverage` writes `results/mechanism_coverage.json`
- [x] `tests/test_taxonomy.py` — inference per known class, tagging idempotency on temp copy,
      coverage counting
- [x] Run live on all 175 definitions; verify loader unaffected

## Validation
- `pytest tests/test_taxonomy.py` green; full suite no regressions; `black --check` clean
- `tag_mechanisms.py --dry-run` after live run reports zero pending changes (idempotent)
- `python scripts/run_backtest.py --use-definitions --strategy hrp` still loads and runs
- `git diff` on `strategy_definitions/` shows ONLY `tags` additions (no renames/removals)

## Rollback
Single commit `Phase 12: mechanism taxonomy + coverage report`.
