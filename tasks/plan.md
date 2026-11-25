# Implementation Plan: On a day (#50)

Spec: [`../specs/on-a-day.md`](../specs/on-a-day.md). Tasks: [`todo.md`](todo.md). (The plan for #49 is in git history.)

## Overview

A task added by hand can go on any day from today on, in any week from the current one on, opened or not, and move between weeks. Mostly a widened rule in `app/tasks/rules.py`, one new query, a change to `bring_back`, and tests proving that opening, closing, the planner and the upcoming list already treat a pinned row right. One PR in the API, `on-a-day`, closing #50; a small docs PR in the parent repo. No schema change, no new route.

## Architecture decisions

- **Two checks, not one.** `day_allowed` becomes "from today on, in the current week or later" (no open-weeks limit). Keeping a task in its own week becomes a separate check, used by `swap` and by `place` for a generated task.
- **A move across weeks is one update of the row in play** (spec decision 3): a new query `MoveTaskWeek` sets `week`, `planned_day` and `placed_by_hand`. Same-week moves keep using `SetTaskWeek`.
- **Another row in the target week is a 409** (decision 4), checked from the task's rows before the update, so the unique constraint never turns it into a 500.
- **`bring_back` needs to know which weeks have opened.** A set-aside row in a week past `planned_through_week` goes back in play on its day; in an open week it goes to the bank, as now. Its two callers (goals, recurring items) pass the owner's marker.
- **Opening, closing, the planner and the upcoming list need no code change** (spec items 5–7, 9): their queries already skip or count a pinned row correctly. Tests prove each; if one fails, the fix goes in that task.

## Tasks

1. **Add on any later day.** `day_allowed`, `landing`; the `addTask` description; `openapi.json`. Tests: three weeks out, yesterday and a wrapped-up week fall back, week read and upcoming leave it out, check-off refused, the add twice. (S)
2. **Move across weeks.** `MoveTaskWeek`, `sqlc generate`; `place` and `check_day`; the `placeTask` description; `openapi.json`. Tests: there and back, later week to later week, each 409, `answerStillMatters` with `schedule`, repeats, a queued move. (M)
3. **Opening and skipping a pinned week.** Tests: opening keeps the row, places recurring work around it and counts it as load; a skipped week carries it over once; dropping a pinned task. (S)
4. **A goal paused and resumed.** `bring_back` and its callers. Tests: back on its day in an unopened week, to the bank in an open one. (S)
5. **Docs and a check.** Spec status and As built; `tasks-week.md`, `week-turnover.md`, `planner.md`, the map; `../docs/` (data model, rule 10, flow 3) on a parent-repo branch. A Sonnet agent runs the four checks and the spec's cases against the running API. (S)

## Checkpoints

- After 1–2: the four checks pass; `openapi.json` differs only in the two descriptions.
- After 3–4: every "What changes" item has a test.
- After 5: the agent's run in the PR; PR "Closes #50"; docs PR open.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| A query assumed rows only exist in open weeks (a read, a close, a count) | A pinned task shows or closes wrongly | Tasks 1 and 3 test each read and close named in the spec; any fix goes in that task |
| Existing tests assume a task can't leave its week | Failures in `test_task_moves.py` | The "a day in another week" case is replaced by the goal session case in task 2 |
| `close_weeks` across several skipped weeks rolls a pinned row more than once | Two carry-overs, "Still matter?" too early | Task 3's skipped-week test counts the `rolled_over` rows |
