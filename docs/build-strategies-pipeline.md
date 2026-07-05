# Build Strategies Pipeline — Agent Teams Architecture

> **Design doc for the `/build-strategies` command using `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`.**

---

## Context

The `/build-strategies` command previously ran as a sequential loop: spawn a one-shot Research sub-agent, select a candidate, optionally spawn a one-shot Builder sub-agent, run backtest, run overfitting, report, loop. Each iteration was fully sequential — no parallelism between research, implementation, backtesting, and analysis.

With `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` enabled, the command is redesigned as a **persistent 4-agent pipeline** where each stage can run concurrently across different strategies.

---

## Pipeline Architecture

```
Orchestrator (main Claude)
  ├── queues: pending[], built[], analyzed[], skip_log[]
  │
  ├──[strategist]  Sonnet  research/backlog.md + mechanism_coverage.json → fills pending[]
  ├──[builder]     Haiku   Implements strategies → fills built[]
  ├──[backtester]  Haiku   Runs run_backtest.py → triggers analyst
  └──[analyst]     Haiku   Runs validate_strategy.py (battery) or run_overfitting.py --param
                           (param sweep) → fills analyzed[]
```

**Research wiring**: the strategist prefers candidates derived from `status: new`
ideas in `research/backlog.md` (reading the full idea file in `research/ideas/` for
the pre-registered hypothesis), tagging such candidates with `research_ref` and
`mechanism`. When no backlog idea is available it still tags every candidate with a
`mechanism`, preferring tags that are underrepresented in `results/mechanism_coverage.json`.
When a `research_ref`-tagged candidate reaches `analyzed[]`, the orchestrator writes
the resulting status (`built` → `validated`/`rejected`) back to both the idea file's
frontmatter and the matching row in `research/backlog.md`.

### Pipeline Parallelism

| Stage | Old (sequential) | New (pipeline) |
|-------|-----------------|----------------|
| Research | Blocks all work | Strategist researches N+1 while Builder works on N |
| Implementation | Blocks backtest | Runs in background; Strategist queues N+2 simultaneously |
| Backtesting | Blocks everything | Analyst checks N while Backtester runs N+1 |
| Overfitting | Sequential after backtest | Overlaps with next strategy's backtest |

---

## Orchestrator State

The orchestrator (main Claude) is the single source of truth — no shared files between agents:

| Variable | Type | Purpose |
|----------|------|---------|
| `pending[]` | list | Researched candidates not yet built |
| `built[]` | list | Built strategies awaiting backtest |
| `analyzed[]` | list | Fully checked strategies awaiting report |
| `skip_log[]` | list | Failed strategies with reasons |
| `strategy_count` | int | Total built this session |
| `*_busy` | bool | Idle/busy flag per agent |

---

## Team Setup

Run once at command start:

```
1. TeamCreate: team_name="strategy-pipeline"
2. Agent(name="strategist",  team_name="strategy-pipeline", model="sonnet")
3. Agent(name="builder",     team_name="strategy-pipeline", model="haiku")
4. Agent(name="backtester",  team_name="strategy-pipeline", model="haiku")
5. Agent(name="analyst",     team_name="strategy-pipeline", model="haiku")
```

The strategist runs on Sonnet (it reads the research backlog and mechanism
coverage data and has to reason about which candidates are worth proposing);
the other three stages are mechanical enough to run on Haiku.

---

## Pipeline Loop Logic

Each orchestrator turn checks and dispatches:

1. **Strategist**: if idle and `pending.length < 2` → `SendMessage("strategist", ...)` with `run_in_background: true`
2. **Builder**: if idle and `pending.length > 0` → pop top candidate → `SendMessage("builder", ...)`
3. **Backtester**: if idle and `built.length > 0` → pop → `SendMessage("backtester", ...)`
4. **Analyst**: after backtester success, determine mode → `SendMessage("analyst", ...)`

### Inbound Message Routing

| Sender | Action |
|--------|--------|
| `strategist` | Sort `research_ref`-tagged candidates first, then JSON-only; deduplicate vs `strategy_definitions/`; push to `pending[]` |
| `builder` | `DONE` → push to `built[]` (carrying `research_ref`/`mechanism` forward); `FAILED` → push to `skip_log[]` |
| `backtester` | `OK` → store metrics, dispatch analyst; `FAIL` → push to `skip_log[]` |
| `analyst` | Push to `analyzed[]`; orchestrator reports to user and, if `research_ref` is set, updates that idea's status in `research/ideas/` + `research/backlog.md` |

---

## Agent Return Formats

**Strategist** returns JSON array:
```json
[{"name":"...", "key":"...", "description":"...", "json_only":true, "reuses_class":"...", "tunable_params":"...", "complexity":"Low|Medium|High", "priority":1, "mechanism":"trend|momentum-cs|mean-reversion|carry|vol-premium|diversification|regime|hedging-overlay|seasonality|meta", "research_ref":"idea-slug (optional)"}]
```

**Builder** returns plain string:
```
DONE: strategy_key=<key> | file=<path> | json_only=<bool> | tunable_params=<or null>
FAILED: strategy_key=<key> | reason=<brief>
```

**Backtester** returns plain string:
```
OK: strategy_key=<key> | return=X% | sharpe=X.XX | maxdd=-X%
FAIL: strategy_key=<key> | error=<brief>
```

**Analyst** returns plain string — format depends on mode:
```
RESULT: strategy_key=<key> | dsr=X.XXX | dsr_verdict=PASS|WARN|FAIL | pbo=X.XX% | pbo_verdict=PASS|WARN|FAIL   (mode=params)
RESULT: key=<key> overall=PASS|WARN|FAIL minbtl=<verdict> dsr=<value>/<verdict> cpcv_prob=<prob> boot_p5=<pct5>  (mode=battery)
SKIP: strategy_key=<key>
ERROR: strategy_key=<key> | reason=<brief>
```

---

## Overfitting Mode Selection

After a successful backtest, the orchestrator decides what to send the analyst:

| Strategy Type | Mode |
|---------------|------|
| `composed` or `portfolio` (JSON-only) | `skip` — N=1 trivially passes DSR |
| `allocation` with tunable params | `params` — `run_overfitting.py --param <variants>` (PBO/DSR across the param grid) |
| `allocation` without tunable params | `battery` (default) — `validate_strategy.py --json` (MinBTL → DSR → CPCV → block bootstrap) |

`battery` replaces the old `n1` mode (a bare `--n-trials 1` DSR run); `params` is
unchanged and stays the exception for candidates with a param grid to sweep, since
the single-config battery doesn't answer the PBO-across-variants question.

Every 5th built strategy, the orchestrator also suggests
`python scripts/run_all_overfitting.py --spa` — a library-wide White's Reality
Check / Hansen's SPA test across all strategies vs. the equal-weight benchmark,
which corrects for the growing number of strategies tried across the whole
session (something no single strategy's battery result can do on its own).

---

## Stop / Cleanup

When user says "stop", "pause", or "enough":
1. Wait for any in-flight backtest to complete
2. `SendMessage` shutdown signal to all 4 agents
3. `TeamDelete("strategy-pipeline")`
4. Print session summary: N strategies built (name, Sharpe, DSR verdict), M skipped (with reason)

---

## Prerequisites

```bash
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
```

Must be set before running `/build-strategies`.

---

## Related Files

| File | Purpose |
|------|---------|
| `.claude/commands/build-strategies.md` | The command implementation |
| `.claude/skills/build-strategies/SKILL.md` | Legacy sub-agent variant (simple fallback) |
| `.claude/skills/build-strategies-auto/SKILL.md` | Unattended inline variant (no agents) |
| `scripts/run_backtest.py` | Backtester script |
| `scripts/validate_strategy.py` | Analyst script — default validation battery mode |
| `scripts/run_overfitting.py` | Analyst script — `params` mode (param sweep) |
| `scripts/run_all_overfitting.py` | Library-wide SPA / Reality Check (every 5th strategy) |
| `research/backlog.md` / `research/ideas/` | Pre-registered idea backlog the strategist draws from |
| `results/mechanism_coverage.json` | Mechanism-tag counts the strategist uses to pick underrepresented mechanisms |
| `strategy_definitions/` | JSON strategy definitions |
| `results/strategies/` | Saved backtest + overfitting/validation results |
