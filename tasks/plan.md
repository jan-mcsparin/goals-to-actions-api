# Implementation Plan: Editing a recurring item moves this week's work (#49)

Spec: [`../specs/recurring-edit.md`](../specs/recurring-edit.md). Tasks: [`todo.md`](todo.md). (The plan for #14 is in git history.)

## Overview

`updateRecurringItem` renames the item's open tasks and, when the schedule changed, reworks each open week's tasks of the item to the new schedule: re-key, move fixed-day tasks, remove extras, make missing ones. Turning an item on reworks too (decision 4). One PR in the API, `recurring-edit`, closing #49; a small docs PR in the parent repo for `docs/flows.md`. No schema change, no new route.

## Architecture decisions

- **A pure rule, like `due.py` and `planner.place`.** `app/turnover/rework.py` takes one week's tasks of the item (key, state, day, placed by hand, a carry-over or not), the new schedule's slots for the week, its fixed day, and today, and returns what to do: new keys, moves, removals, slots to make. No database, no clock; tested by example.
- **Only when the schedule changed.** Kind, weekday, day of month, times, period or `startsOn`. A rename or a new aspiration alone reworks nothing. This also makes a second identical edit change nothing.
- **What the week is due is counted from its Monday** (or `startsOn` if later), not from today: an edit on Saturday to a 3-a-week item still wants 3, so nothing done is "extra". Missing ones are placed on days after today, or wait in the bank (spec 2). The spec's wording is corrected to say so.
- **A week's own tasks** are its rows whose task didn't roll over into it, plus a flexible task carrying inside its period (its key matches the period the schedule *before* the edit gives that week). Everything else in the week is a carry-over and is only renamed (decision 3).
- **Keys stay unique, deleted rows included** (`tasks_item_period_number`). The survivors take the new schedule's slots in order (done, placed by hand, on a day, in the bank); a removed task is first moved to a number past any in use, then soft-deleted, so the new slots are free and nothing removed is made again. Survivors beyond the count (done or placed by hand) also get numbers past the slots.
- **A move is an edit write, not a planner write,** like `fill_item`'s "due today goes on today": a new query moves a row the app placed (or in the bank) to a day from today on. Missing tasks go through `place_new_work` from tomorrow, a due-today fixed one on today, as `fill_item` does now.
- **`updateRecurringItem` asks for `Today`,** so it needs `X-Time-Zone`, as create already does.

## Tasks

1. **The pure rule.** `app/turnover/rework.py` and `tests/test_rework.py`. (M)
2. **Rename, and fixed-day tasks move.** Queries (rename open tasks; list the item's tasks in a week; re-key a task; move a row), `sqlc generate`; `rules.update` with `today`; the route with `Today`; `openapi.json`. Replaces the "edit leaves this week's task" test. (M)
3. **Counts, and a change of kind or period.** Removing extras and making missing ones, through the API; next week in the same period makes nothing more. (M)
4. **Off and on; two open weeks; repeats.** An edit to an off item renames only; turning on reworks. Sunday evening, both weeks follow; today untouched. `test_repeats.py` compares the week's rows; the lock test line keeps working; audit action. (S)
5. **Docs and a check.** Spec status and As built; `recurring-items.md`, `week-turnover.md`, `planner.md`, the map; `../docs/flows.md` flow 4 on a parent-repo branch. A Sonnet agent runs the four checks and the spec's cases against the running API. (S)

## Checkpoints

- After 1–2: the four checks pass; a weekly item's day change shows on the week read.
- After 3–4: the four checks pass; every "What changes" item has a test.
- After 5: agent's run recorded in the PR; PR "Closes #49"; docs PR open.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Edited while off, a flexible task carrying inside its period isn't recognised on turn-on (its key is the old schedule's), so it's treated as a carry-over and a fresh one is made | Low: one extra task, only after edit-off-change-on mid-period | Accepted; noted in the spec |
| Re-keying hits the unique index | A 500 | Two-phase re-key (out of the way, then into place); a test that edits back and forth |
| An existing test or front-end mock assumes edits move nothing | Test failures | The old test is replaced in task 2; the mock's edit is #76's work |
