---
name: clearplan
description: Start a new GSD plan — clears the plan/ folder and scaffolds milestones, phase files, an index, and a state tracker
argument-hint: <brief description of the new plan>
---

**IMPORTANT: This skill is user-initiated only. Claude must never call `/clearplan` automatically.** It permanently deletes all existing plan files. Only proceed because the user explicitly invoked this skill.

You are creating a new GSD (Get Stuff Done) plan. Follow these steps exactly.

## Step 1 — Clarify the plan

If no argument was provided, use AskUserQuestion to ask the user what the plan is for before continuing.

If an argument was provided, treat it as the plan title/description and proceed.

## Step 2 — Design the milestones

Think through the work and break it into **3–7 major phases** (milestones). Each phase should represent a meaningful, independently completable chunk of work. For each phase, define:
- A short slug (e.g. `phase-01-data-layer`)
- A title
- 3–8 concrete TODO items (actionable, specific tasks)

## Step 3 — Clear the plan folder

Delete all files currently inside the `plan/` directory by running:
```
rm -f plan/*.md
```
If the `plan/` folder does not exist, create it:
```
mkdir -p plan
```

## Step 4 — Write the phase files

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

## Step 5 — Write the index file

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

## Step 6 — Write the state file

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

## Step 7 — Confirm

Tell the user the plan has been created, summarise the phases, and say they can run `/continueplan` to begin work.
