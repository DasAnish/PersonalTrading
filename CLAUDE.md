# PersonalTrading - Claude Development Context

> **IMPORTANT: NEVER send orders into IB Gateway.** This project is for experimentation and research only. All orders must be entered manually by the user. Claude must never place, submit, or trigger any trade orders programmatically.

> **IMPORTANT: No automated order execution — ever.** This project is purely for experimentation and research. The user will always enter orders manually via the IB Gateway UI. Claude must only generate rebalance reports and recommendations; it must never programmatically place, submit, modify, or cancel any trade orders.

---

## GSD Planning

This project uses a **Get Stuff Done (GSD)** planning pattern. Every significant piece of work is captured as a structured plan before execution begins.

### Commands

| Command | Usage | Description |
|---------|-------|-------------|
| `/clearplan` | `/clearplan <description>` | Start a new plan — clears `plan/` and scaffolds milestones, phase files, index, and state |
| `/newplan` | `/newplan <description>` | Create a new plan and immediately begin executing the first phase |
| `/continueplan` | `/continueplan` | Resume the active plan from the current TODO in the current phase |
| `/build-strategies` | `/build-strategies` | Research and build new trading strategies in a continuous loop |

### Plan folder structure

```
plan/
├── index.md              # Master index: all phases, statuses, and every TODO
├── state.md              # Current phase, current TODO, progress counts
├── phase-01-<slug>.md    # Phase 1 milestone with TODOs and notes
├── phase-02-<slug>.md    # Phase 2 ...
└── ...
```

### Workflow

0. Create a findings.md that can be used as context for future continue plan runs
1. Describe the work → run `/clearplan <description>`
2. Claude breaks it into **3–7 phases**, writes all files, confirms the plan
3. Run `/continueplan` at the start of each session to pick up where you left off
4. Claude marks each TODO `[x]` and updates `state.md` as work completes
5. When a phase finishes, `index.md` is updated and the next phase begins
6. Commit the code changes between each phase

### Rules

- `/clearplan` is **user-initiated only** — Claude must never invoke it automatically. It is a destructive reset and must only run when the user explicitly calls `/clearplan`.
- When Claude enters plan mode on its own (e.g. to think through a task), it must **update** the existing plan files rather than clearing them.
- If no `plan/` folder exists yet, Claude may create it and scaffold the files — but only when the user has explicitly asked for a new plan.
- `state.md` is the single source of truth for current position in the plan
- Phase files are the single source of truth for TODO completion within a phase
- Claude must update both files after every completed TODO, never in batch

---

## Clarification

- When requirements are ambiguous or a task has multiple valid interpretations, use AskUserQuestion to clarify before proceeding.
- Before making major design decisions, confirm assumptions with AskUserQuestion.

---

## Documentation

| Topic | File |
|-------|------|
| Project overview, components, IB connection, backtesting specs | [docs/project.md](docs/project.md) |
| Strategy architecture, algorithms, composability | [docs/strategies.md](docs/strategies.md) |
| CLI reference (all 4 modes + examples) | [docs/cli.md](docs/cli.md) |
| Web dashboard usage & API | [docs/dashboard.md](docs/dashboard.md) |
| Session log, next actions, known bugs | [docs/session_log.md](docs/session_log.md) |
| Full file/directory reference | [docs/project-structure.md](docs/project-structure.md) |
| Session history | `ai_iterations/` |
| Architecture decisions | `decisions/` |

---

## Code Standards

- Black formatting, line length 88
- Async/await throughout
- Type hints preferred
- pytest + pytest-asyncio for tests
- Logging: DEBUG/INFO/WARNING/ERROR levels
