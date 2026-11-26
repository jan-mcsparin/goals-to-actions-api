# Implementation Plan: Any week (#51)

Spec: [`../specs/any-week.md`](../specs/any-week.md). Tasks: [`todo.md`](todo.md). (The plan for #50 is in git history.)

## Overview

`getWeek` reads any week by its status (`closed`, `open`, `notOpen`) and every read says how full the week is. The `Week` and `Task` models grow by addition; a handful of new read queries, each over a range of days so `coming-up` (#52) can reuse them; the expected counts' pure rules beside `app/turnover/due.py`'s. One PR in the API, `any-week`, closing #51; a small docs PR in the parent repo. No schema change, no new route.

## Architecture decisions

- **One week query for every status.** `ListWeekTasks` also returns rolled-over and lapsed rows, with `task_weeks.outcome` as `week_outcome`; the other `Task` reads select a null one. An open week has no such rows, so open weeks read as now.
- **Status from the markers, in `app/weeks.py`.** `week_status(week, weeks)` beside `open_weeks`: before the current week is `closed`, in `OpenWeeks` is `open`, else `notOpen`.
- **Progress by status.** Open: as now. Closed: goals with a target that week and a session row in it, whatever their status (decision 2), from a new query. Not open: none.
- **Counts in a new `app/tasks/fullness.py`.** Actual counts from the tasks the read returns (week and per day). Expected counts call pure rules added to `app/turnover/due.py` (`expected_sessions`, `expected_item_tasks` with decision 1), the same `goal_slots` and `item_slots` opening calls, so the two can't drift.
- **Dated items in a new `app/tasks/dated.py`.** Occurrences (fixed-day items worked out with `fixed_day`, `notOpen` only), check-ins and deadlines (every week, active goals only).
- **Range queries** (`from`, `through`): `ListPinnedOrDue`, `ListMilestoneDates`, `ListDeadlines`, `GoalsWithSessions`, plus `FirstWeek`.

## Tasks

1. **Week status, past rows, `firstWeek`.** `ListWeekTasks` with outcomes; `weekOutcome`; `status`; `firstWeek`; closed-week Progress (decision 2); a `notOpen` week has no goals. (M)
2. **Late check-offs.** Tests only, unless one fails. (S)
3. **Actual counts.** `counts` and `days[].counts` for closed and open weeks; `null` day counts for `notOpen`. (S)
4. **Expected counts.** Pure rules and their tests; `ListPinnedOrDue`; the read for `notOpen`; the "then opened" test. (M)
5. **Occurrences, check-ins, deadlines.** `dated.py`, two queries, three models. (M)
6. **Docs and a check.** Spec status and As built, the map, `tasks-week.md`; parent-repo docs on a branch; another user's rows in a past and a later week; a Sonnet agent runs the checks and the spec's cases against the running API. (S)

## Checkpoints

- After 1–3: the four checks pass; `openapi.json` changes only by addition.
- After 4–5: every row of the status table, each count rule and each decision has a test.
- After 6: the agent's run in the PR; PR "Closes #51"; docs PR open.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Returning rolled-over rows from `ListWeekTasks` changes something that reads it for an open week (the full-day mark, the planner's load) | A wrong cap or placement | Only `week_read` calls it (checked in task 1); open weeks never hold those rows |
| A late check-off on a twice-rolled task picks the wrong row | Done in the wrong week, or a 409 | Task 2 runs first after the read; a fix goes in that task with an "As built" note |
| Expected and actual counts drift | Coming up and Week disagree with what opening makes | Shared pure rules, and task 4's test opens the same setup and compares |
| A set-aside or dropped row changes `firstWeek` or the list | A week reads wrong | `firstWeek` counts every row (decision 5); the list still leaves set-aside and dropped out; both tested |
