---
name: newplan
description: Create a new GSD plan and immediately begin executing the first phase
argument-hint: <brief description of the new plan>
---

**IMPORTANT: This skill is user-initiated only. Never call `/newplan` automatically.**

You are creating a new GSD plan and then immediately starting execution. This is equivalent to running `/clearplan` followed by `/continueplan` in a single step.

## Part 1 — Create the plan (same as `/clearplan`)

Follow every step of the `clearplan` skill exactly:

### Step 1 — Clarify the plan

If no argument was provided, use AskUserQuestion to ask the user what the plan is for before continuing.

If an argument was provided, treat it as the plan title/description and proceed.

### Step 2 — Design the milestones

Think through the work and break it into **3–7 major phases** (milestones). Each phase should represent a meaningful, independently completable chunk of work. For each phase, define:
- A short slug (e.g. `phase-01-data-layer`)
- A title
- 3–8 concrete TODO items (actionable, specific tasks)

### Step 3 — Clear the plan folder

Delete all files currently inside the `plan/` directory by running:
```
rm -f plan/*.md
```
If the `plan/` folder does not exist, create it:
```
mkdir -p plan
```

### Step 4 — Write the phase files

For each phase, write a file `plan/phase-NN-<slug>.md` with this structure:

```markdown
# Phase N — <Title>

## Goal
One sentence describing what this phase achieves.

## TODOs
- [ ] Task 1
- [ ] Task 2
- [ ] Task 3
...

## Notes
(empty — filled in during execution)
```

### Step 5 — Write the index file

Write `plan/index.md`:

```markdown
# Plan: <Plan Title>

**Created**: <today's date>
**Status**: In Progress

## Milestones

| # | Phase | Status |
|---|-------|--------|
| 1 | [Phase 1 Title](phase-01-<slug>.md) | ⬜ Not Started |
| 2 | [Phase 2 Title](phase-02-<slug>.md) | ⬜ Not Started |
...

## All TODOs

### Phase 1 — <Title>
- [ ] Task 1
- [ ] Task 2
...

### Phase 2 — <Title>
...
```

### Step 6 — Write the state file

Write `plan/state.md`:

```markdown
# Plan State

**Current Phase**: 1
**Current Phase File**: plan/phase-01-<slug>.md
**Current TODO**: Task 1 of Phase 1
**Last Updated**: <today's date>

## Progress
- Phase 1: 0/<N> TODOs complete
- Phase 2: 0/<N> TODOs complete
...
```

### Step 7 — Confirm the plan

Tell the user the plan has been created and summarise the phases. Then immediately proceed to Part 2 without waiting.

---

## Part 2 — Begin executing the plan (same as `/continueplan`)

Do not ask the user whether to start. Begin immediately.

Follow every step of the `continueplan` skill exactly:

1. Read `plan/state.md` to find the current phase and current TODO.
2. Read the current phase file to understand the full list of TODOs and any notes.
3. Execute the first incomplete TODO. Complete real work — write code, run commands, edit files — do not just describe what needs to be done.
4. When the TODO is done, mark it `[x]` in the phase file and update `state.md` (current TODO advances to the next item, last updated date updated, progress counts updated).
5. Continue to the next TODO and repeat until you reach a natural stopping point (end of phase, blocker, or the user interrupts).
6. If a phase is fully complete, mark it `✅ Done` in `plan/index.md` and update `state.md` to point to the next phase.
