---
name: continueplan
description: Pick up the active GSD plan from where it was left off — reads the state file and resumes the current phase and TODO
---

You are resuming an active GSD plan. Follow these steps exactly.

## Step 1 — Load the plan state

Read `plan/state.md`. If it does not exist, tell the user there is no active plan and suggest running `/clearplan <description>` to create one, then stop.

## Step 2 — Load the current phase

Read the phase file listed in `plan/state.md` under **Current Phase File**.

Read `plan/index.md` to get the full picture of milestones and overall progress.

## Step 3 — Orient the user

Show a brief status summary:
- Plan title (from index.md)
- Which phase we are on and its title
- Completed vs total TODOs in this phase
- The next unchecked TODO item

## Step 4 — Execute the next TODO

Work through the next unchecked `- [ ]` item in the current phase file. When the task is done:
1. Mark it `- [x]` in the phase file
2. Update `plan/state.md` — set **Current TODO** to the next unchecked item (or "Phase complete" if none remain)
3. Update the progress counts in `plan/state.md`

## Step 5 — Phase completion

When all TODOs in the current phase are checked off:
1. Update `plan/index.md` — change the phase status from `⬜ Not Started` / `🔄 In Progress` to `✅ Complete`
2. Advance **Current Phase** and **Current Phase File** in `plan/state.md` to the next phase
3. If there is no next phase, set **Current Phase** to `Complete` and congratulate the user — the plan is done
4. Otherwise, tell the user Phase N is complete and ask if they want to continue to the next phase now or stop here

## Step 6 — Mark in-progress

Whenever a phase is started but not yet complete, update its status in `plan/index.md` to `🔄 In Progress`.

## Notes
- Always update the state and phase files after each TODO — never leave them out of sync with actual progress
- If you need clarification on a TODO item, use AskUserQuestion before attempting it
