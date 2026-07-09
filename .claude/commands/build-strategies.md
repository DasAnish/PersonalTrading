---
description: Research and build new trading strategies — research-scan on the main thread, then 2 strategy-builder agents iterating configs/params via the dashboard REST API
---

**IMPORTANT — no prompts, no orders:** Do not ask the user for permissions; they may be away. Never place, submit, modify, or cancel any trade order. Research and reporting only.

# Strategy Builder (Consolidated)

Two-phase workflow, replacing the old 4-agent pipeline team:

1. **Research (main thread, inline)** — run the `/research-scan` skill yourself.
2. **Build (2 parallel `strategy-builder` agents)** — each agent implements
   candidates and iterates configurations/parameters, using the dashboard REST
   API for backtest + validation + overfitting.

---

## Context (read fresh every session — never trust pasted lists)

- **Assets**: `strategy_definitions/assets/` (one JSON per investable asset).
- **Universe groups**: `strategy_definitions/universe.json` — groups `equity`,
  `bond`, `commodity`, `europe_equity`, `em_equity`, `all`. Definitions
  reference groups as `"underlying": "universe:<group>"` (resolved at load
  time). Never hand-copy a group's assets into a definition.
  - Order-sensitive classes (e.g. `ProtectiveAssetAllocationStrategy` treats
    the **last** resolved asset as the safe asset): group refs first, fixed
    asset last. Never point such a class at `universe:all`.
  - Bespoke baskets: list `assets/<key>` refs explicitly, or add a new named
    group to `universe.json` if reusable.
- **Strategy classes**: `strategies/__init__.py` for the roster,
  `docs/strategies.md` for descriptions.
- **Existing definitions**: list
  `strategy_definitions/{allocations,composed,portfolios,overlays}/` at the
  start; an existing key must never be proposed again.
- **Architecture**: `AllocationStrategy.calculate_weights(context)` computes
  weights; `OverlayStrategy` transforms an underlying's weights. New strategy =
  Python class in `strategies/` (if a new algorithm) + JSON definition in
  `strategy_definitions/<subfolder>/`.

---

## Phase 1 — Research (main thread)

1. Invoke the `research-scan` skill (default scope, or the user's argument).
   It writes idea files to `research/ideas/` and rows to `research/backlog.md`.
2. Build the candidate list (target 6–10 candidates):
   - Every `status: new` idea in `research/backlog.md` (read its idea file for
     the pre-registered hypothesis) — these carry `research_ref`.
   - Read `results/mechanism_coverage.json` and favour under-represented
     mechanisms (e.g. carry/seasonality over trend/meta).
   - **Old-strategy variants**: existing classes with untried parameters
     (lookbacks, top_n, linkage, vol targets) or re-scoped to an untried
     `universe:` group. Cross-check against existing definition keys.
3. Each candidate is a JSON object:
   ```json
   {
     "name": "...", "key": "file_slug", "subfolder": "allocations|composed|portfolios",
     "description": "one sentence", "json_only": true,
     "reuses_class": "ClassName or null", "new_python_class": "ClassName or null",
     "tunable_params": "param=v1,v2,v3 or null",
     "mechanism": "trend|momentum-cs|mean-reversion|carry|vol-premium|diversification|regime|hedging-overlay|seasonality|meta",
     "research_ref": "idea-slug (omit if not from backlog)"
   }
   ```
4. Order: `research_ref` candidates first, then `json_only`, then new-class.
   Split the list into two halves — one per builder. **All candidates needing
   a new Python class go to builder 1 only** (both builders editing
   `strategies/__init__.py` concurrently causes conflicts).
5. For each dispatched candidate with a `research_ref`: set that idea's
   frontmatter `status: candidate` and update its `research/backlog.md` row.

## Phase 2 — Build (2 agents)

Ensure the dashboard server is up first (`curl -s localhost:5000/api/strategies`
— if down, start it detached: `python scripts/serve_results.py`).

Spawn **two** agents (`subagent_type: "general-purpose"`, haiku model,
`run_in_background: true`), named `builder-1` and `builder-2`, each with its
half of the candidate list and this prompt template:

```
Respond terse like smart caveman: drop articles and filler, keep all technical
substance exact, quote errors verbatim, no pleasantries. Code/JSON stay normal.

You are strategy-builder-<N> for the PersonalTrading repo. NEVER place, submit,
modify, or cancel any trade order. Research only. Do not ask the user anything.

CANDIDATES (work through in order, one at a time):
<candidate JSON list>

FOR EACH candidate:
1. Implement it.
   - json_only: write strategy_definitions/<subfolder>/<key>.json, using an
     existing file in that subfolder as the schema template. Reference universe
     groups ("universe:<group>") instead of copying asset lists.
   - new Python class (builder-1 only): read the most similar file in
     strategies/ and strategies/core.py, write strategies/<snake>.py, add the
     import+__all__ entry to strategies/__init__.py, then write the JSON
     definition.
2. Run the pipeline via the dashboard REST API (this picks up fresh code —
   do NOT run the scripts directly):
     curl -s -X POST localhost:5000/api/run/<key>
   Response has job_id. Poll every ~30s:
     curl -s localhost:5000/api/run/status/<job_id>
   until state is "done" or "failed" (steps: backtest -> validate ->
   overfitting; a full run takes minutes).
3. On "failed": read the log tail in the status payload (full logs under
   results/jobs/<job_id>/), fix your implementation, resubmit once. If it
   fails again, record the reason and move on.
4. On "done": record from results: metrics (total_return, sharpe_ratio,
   max_drawdown), validation overall verdict, overfitting DSR/PBO verdicts.
5. Iterate configurations: if the result is promising (Sharpe > 0.8 and
   validation not FAIL) and tunable_params is set, create 1-2 parameter or
   vol-target variants as new definitions (new keys, same rules as above) and
   run them through the same REST pipeline. Do not exceed 3 variants per
   candidate.
6. If the candidate has research_ref: update research/ideas/<research_ref>.md
   frontmatter status and the matching research/backlog.md row:
   built -> validated (verdict PASS/WARN) or rejected (FAIL).

RETURN when list exhausted: one line per strategy attempted:
<key> | built|failed | sharpe=X.XX | maxdd=-X% | validation=PASS/WARN/FAIL | overfitting=PASS/WARN/FAIL/skip | note
```

## Orchestration (main thread)

- While builders run, wait for their completion notifications; on each
  builder's return, verify its report: spot-check that
  `strategy_definitions/` files exist and `results/strategies/<key>/` is
  populated for claimed builds.
- If a builder dies or stalls, re-spawn it with its remaining candidates.
- When both finish: run `python scripts/run_full_analysis.py --skip-backtest
  --skip-validate` once for the library-wide SPA refresh, then summarise for
  the user: built/failed table, verdicts, and any backlog status changes.
- Commit per milestone (definitions + any new classes) with a descriptive
  message.

## Rules

- Never duplicate an existing definition key.
- Only assets present in `strategy_definitions/assets/`.
- Builders must use the REST API for all backtest/validation/overfitting runs.
- Stop immediately on "stop"/"pause"/"enough" and summarise.
