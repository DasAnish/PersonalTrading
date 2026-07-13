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

## Phase 2 — Build & submit (2 agents)

**Builders do NOT wait for pipeline results.** Their job is to implement each
candidate and *submit* its run (fire-and-forget), then move on. Backtest →
validate → overfitting keep running in the background; results are collected
later in Phase 3 (when the user asks, or before the SPA refresh/commit). This
keeps builders fast and lets a batch of candidates run their pipelines
concurrently instead of one builder blocking on each ~minutes-long run.

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
2. Submit the pipeline run via the dashboard REST API — do NOT wait for it to
   finish (this picks up fresh code — do NOT run the scripts directly):
     curl -s -X POST localhost:5000/api/run/<key>
   Capture job_id from the response. Do ONE status poll ~5s later
     curl -s localhost:5000/api/run/status/<job_id>
   ONLY to catch an immediate load/submission failure (state "failed" with a
   config/JSON/import error in the log tail — the strategy never started
   backtesting). If it failed to load, fix your implementation and resubmit
   once. Otherwise record <key> + job_id and move straight to the next
   candidate. Do NOT poll to completion.
3. Do NOT read metrics, do NOT create parameter/vol-target variants, and do NOT
   touch research/ backlog verdicts — all of that needs finished results and is
   done later in the collect phase, not by you.

RETURN when list exhausted: one line per candidate:
<key> | submitted|load-failed|not-built | job_id=<id or -> | note
(include any candidate you could not implement at all, with the reason)
```

## Phase 3 — Collect results & finalize (deferred, main thread)

Run this once the pipelines have had time to finish — either when the user asks
to see results, or immediately before the SPA refresh/commit. Do NOT block the
build on it.

1. For each submitted `job_id`, poll `curl -s localhost:5000/api/run/status/<job_id>`
   until state is "done" or "failed" (a full run takes minutes; several run
   concurrently). On "failed", read the log tail (full logs under
   `results/jobs/<job_id>/`) and record the reason.
2. For each "done" key, read `results/strategies/<key>/` yourself — metrics
   (total_return, sharpe_ratio, max_drawdown), validation `overall` verdict,
   overfitting DSR/PBO verdicts. **Do not trust a builder's or a prior report's
   verdict — read the verdict files directly** (haiku builders have
   misreported PASS/WARN/FAIL).
3. Promote promising configs: if a result is promising (Sharpe > 0.8 and
   validation not FAIL) and the candidate had `tunable_params`, create 1–2
   parameter/vol-target variants as new definitions (new keys) and submit them
   through the same REST pipeline; re-collect. Max 3 variants per candidate.
4. For each candidate with `research_ref`: update
   `research/ideas/<research_ref>.md` frontmatter status and the matching
   `research/backlog.md` row: `built` -> `validated` (verdict PASS/WARN) or
   `rejected` (FAIL).

### Triggering Phase 3 (don't sit and poll)

Once builders return their `job_id`s, don't block the chat polling status.
Pick a trigger by how long you expect to wait:

- **Auto-ping this session (preferred while active):** after both builders
  return their `job_id`s, start a `Monitor` on the poller script — it prints one
  status line per round and a final `ALL DONE ...` line when every job reaches a
  terminal state (done/failed/interrupted/unknown), which wakes the
  conversation. Then run Phase 3. Concretely:

  ```
  Monitor(
    description="build pipelines -> Phase 3 collect",
    command="python scripts/wait_jobs.py <job_id_1> <job_id_2> ... [--interval 20]"
  )
  ```

  `scripts/wait_jobs.py` polls `localhost:5000/api/run/status/<job_id>` for each
  id, dedupes, treats a 404 as terminal, and self-terminates on `ALL DONE` or
  after `--max-rounds` (default 180 × 20s ≈ 1h). No fixed manual checking — the
  `ALL DONE` event is the trigger to collect. Do not spawn a short-interval
  Monitor just to keep the session warm; one watch over the real job_ids is
  enough.
- **Detached / overnight (session may be closed):** schedule a cloud agent
  (`/schedule` or a cron routine) that runs Phase 3 — poll jobs, read verdicts,
  update backlog, commit. It runs in its own context (it won't ping *this*
  chat; it does the work and reports in its own run). Use when the build was
  kicked off unattended.
- **On demand:** just run Phase 3 by hand next time the user asks for results.

Keep the submitted `key -> job_id` map (from the builders' return lines) so any
of these can find the jobs later.

## Orchestration (main thread)

- While builders run, wait for their completion notifications; on each
  builder's return, verify its report: spot-check that the claimed
  `strategy_definitions/` files actually exist. (Results won't be populated yet
  — that's expected; builders no longer wait for them.)
- If a builder dies or stalls, re-spawn it with its remaining candidates.
- When both builders finish, run Phase 3 to collect results and update
  verdicts/backlog, then run `python scripts/run_full_analysis.py
  --skip-backtest --skip-validate` once for the library-wide SPA refresh, and
  summarise for the user: built/failed table, verdicts (read directly), and any
  backlog status changes.
- Commit per milestone (definitions + any new classes) with a descriptive
  message.

## Rules

- Never duplicate an existing definition key.
- Only assets present in `strategy_definitions/assets/`.
- Builders must use the REST API to submit all runs (never run the scripts
  directly), but must NOT block on the results — collection is Phase 3.
- Verdicts go into the summary only after being read directly from the result
  files, never from a builder's self-report.
- Stop immediately on "stop"/"pause"/"enough" and summarise.
