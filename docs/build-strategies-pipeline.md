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
  ├──[strategist]  Sonnet  Research candidates → fills pending[]
  ├──[builder]     Haiku   Implements strategies → fills built[]
  ├──[backtester]  Haiku   Runs run_backtest.py → triggers analyst
  └──[analyst]     Haiku   Runs run_overfitting.py → fills analyzed[]
```

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
2. Agent(name="strategist",  team_name="strategy-pipeline", model="haiku")
3. Agent(name="builder",     team_name="strategy-pipeline", model="haiku")
4. Agent(name="backtester",  team_name="strategy-pipeline", model="haiku")
5. Agent(name="analyst",     team_name="strategy-pipeline", model="haiku")
```

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
| `strategist` | Sort by JSON-only first; deduplicate vs `strategy_definitions/`; push to `pending[]` |
| `builder` | `DONE` → push to `built[]`; `FAILED` → push to `skip_log[]` |
| `backtester` | `OK` → store metrics, dispatch analyst; `FAIL` → push to `skip_log[]` |
| `analyst` | Push to `analyzed[]`; orchestrator reports to user |

---

## Agent Return Formats

**Strategist** returns JSON array:
```json
[{"name":"...", "key":"...", "description":"...", "json_only":true, "reuses_class":"...", "tunable_params":"...", "complexity":"Low|Medium|High", "priority":1}]
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

**Analyst** returns plain string:
```
RESULT: strategy_key=<key> | dsr=X.XXX | dsr_verdict=PASS|WARN|FAIL | pbo=X.XX% | pbo_verdict=PASS|WARN|FAIL
SKIP: strategy_key=<key>
ERROR: strategy_key=<key> | reason=<brief>
```

---

## Overfitting Mode Selection

After a successful backtest, the orchestrator decides what to send the analyst:

| Strategy Type | Mode |
|---------------|------|
| `composed` or `portfolio` (JSON-only) | `skip` — N=1 trivially passes DSR |
| `allocation` with tunable params | `params` — run with `--param <variants>` |
| `allocation` without tunable params | `n1` — run with `--n-trials 1` |

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
| `scripts/run_overfitting.py` | Analyst script |
| `strategy_definitions/` | JSON strategy definitions |
| `results/strategies/` | Saved backtest + overfitting results |
