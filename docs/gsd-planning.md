# GSD Planning

This project uses a **Get Stuff Done (GSD)** planning pattern. Every significant piece of work is captured as a structured plan before execution begins.

## Commands

| Command | Usage | Description |
|---------|-------|-------------|
| `/clearplan` | `/clearplan <description>` | Start a new plan — clears `plan/` and scaffolds milestones, phase files, index, and state |
| `/newplan` | `/newplan <description>` | Create a new plan and immediately begin executing the first phase |
| `/continueplan` | `/continueplan` | Resume the active plan from the current TODO in the current phase |
| `/build-strategies` | `/build-strategies` | Research and build new trading strategies in a continuous loop |

## Plan folder structure

```
plan/
├── index.md              # Master index: all phases, statuses, and every TODO
├── state.md              # Current phase, current TODO, progress counts
├── phase-01-<slug>.md    # Phase 1 milestone with TODOs and notes
├── phase-02-<slug>.md    # Phase 2 ...
└── ...
```

## Workflow

0. Create a `findings.md` that can be used as context for future `/continueplan` runs
1. Describe the work → run `/clearplan <description>`
2. Claude breaks it into **3–7 phases**, writes all files, confirms the plan
3. Run `/continueplan` at the start of each session to pick up where you left off
4. Claude marks each TODO `[x]` and updates `state.md` as work completes
5. When a phase finishes, `index.md` is updated and the next phase begins
6. Commit the code changes between each phase

## Rules

- `/clearplan` is **user-initiated only** — Claude must never invoke it automatically. It is a destructive reset and must only run when the user explicitly calls `/clearplan`.
- When Claude enters plan mode on its own (e.g. to think through a task), it must **update** the existing plan files rather than clearing them.
- If no `plan/` folder exists yet, Claude may create it and scaffold the files — but only when the user has explicitly asked for a new plan.
- `state.md` is the single source of truth for current position in the plan
- Phase files are the single source of truth for TODO completion within a phase
- Claude must update both files after every completed TODO, never in batch
