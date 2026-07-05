# Phase 11 — Research Infrastructure (/research-scan + Idea Backlog)

**Model**: sonnet

## Goal
Open the closed strategy-sourcing loop. Create a reviewable research backlog with
pre-registered hypotheses and a standalone `/research-scan` skill that web-searches quant
literature and writes idea files. No Python code; markdown schema + skill authoring only.

## TODOs
- [x] `research/README.md` — document the idea-file schema (frontmatter: title, source,
      mechanism, status new|candidate|built|validated|rejected, date_added; body sections:
      Hypothesis (pre-registered), Rule sketch, Universe fit)
- [x] `research/backlog.md` — index table: slug | mechanism | status | source | date added
- [x] 2–3 seed idea files in `research/ideas/`: one canonical citation for an
      already-implemented strategy marked `built` (e.g. dual momentum, Antonacci 2014),
      one genuinely new idea marked `new` (implementable long-only on the 13 UK ETFs,
      monthly rebalance)
- [x] `.claude/skills/research-scan/SKILL.md` — WebSearch/WebFetch over arXiv q-fin, SSRN,
      AQR/Robeco/Man/Alpha Architect, quant blogs; optional topic scope via args; dedupe
      against backlog.md AND strategy_definitions/; write idea file with hypothesis BEFORE
      any backtest; update backlog index; cap ~5 ideas/run; NEVER touch strategy_definitions/
      or run backtests (research only)

## Validation
- All frontmatter blocks parse as YAML (`python -c` with yaml.safe_load on each idea file)
- README schema matches the seed files field-for-field
- Skill file follows existing format (compare `.claude/skills/rebalance/SKILL.md`)
- `git status` shows changes ONLY under `research/` and `.claude/skills/research-scan/`

## Rollback
Single commit `Phase 11: research infrastructure (/research-scan + idea backlog)`.
