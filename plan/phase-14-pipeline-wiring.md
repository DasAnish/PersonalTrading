# Phase 14 — Pipeline Wiring + Dashboard

**Model**: sonnet (build-strategies.md prompt surgery) + haiku (dashboard card, docs)

## Goal
Wire the research backlog, mechanism coverage, and validation battery into the live
`/build-strategies` pipeline; surface validation.json on the dashboard; refresh docs.

## TODOs
- [x] `.claude/commands/build-strategies.md` — strategist stage: read `research/backlog.md`
      (prefer status:new ideas; carry `research_ref` + hypothesis into candidate JSON) and
      `results/mechanism_coverage.json` (prefer underrepresented mechanisms); fall back to
      current recombination behavior when no new ideas. Candidate JSON gains optional
      `research_ref` and `mechanism` fields.
- [x] Same file — analyst stage: replace run_overfitting.py call with
      `python scripts/validate_strategy.py --strategy <key> --json`; RESULT format
      `RESULT: key=… overall=PASS|WARN|FAIL minbtl=… dsr=… cpcv_prob=… boot_p5=…`;
      `skip` mode unchanged for json_only composed/portfolios.
- [x] Same file — orchestrator loop: on PASS/WARN with research_ref, update idea file status
      (new→built→validated/rejected); every 5th strategy suggest
      `python scripts/run_all_overfitting.py --spa`. Align docs/build-strategies-pipeline.md
      model table (command file wins: strategist=sonnet, rest=haiku).
- [x] Dashboard: validation battery card in `scripts/server/templates/strategy.html` +
      static JS (four test rows + overall badge); extend per-strategy API payload
      (`scripts/server/api.py`/`data.py`) to include validation.json following the
      stress_test.json pattern.
- [x] Docs: `docs/overfitting.md` "Validation battery" section; `docs/strategies.md`
      mechanism taxonomy table; `docs/cli.md` new commands; `CLAUDE.md` Quick Reference
      gains a research/ row.

## Validation
- Full `pytest` green; `black --check` clean
- Dashboard smoke: `/api/strategy/<key>` includes validation block; strategy page renders card
- build-strategies.md diff reviewed line-by-line: no weakening of "never place orders"
  constraints (grep order-placement verbs, as in Phases 5/10)
- Docs cross-links resolve

## Rollback
Single commit `Phase 14: pipeline wiring + dashboard`.
