# Implementation Plan: Week turnover (#9)

Spec: [`../specs/week-turnover.md`](../specs/week-turnover.md). Tasks: [`todo.md`](todo.md). Planned together with the front end's #30, #46 and #35 ([`../../web-frontend/tasks/plan.md`](../../web-frontend/tasks/plan.md)), which build on this contract. (The plan for #8 is in git history.)

## Overview

Weeks open and close. A week opens at 6 p.m. on the Sunday before it and fills its bank: goal sessions, recurring tasks, and upcoming tasks now due. It closes when its Sunday ends, or when the person wraps it up. At the close, each unfinished task rolls over or lapses by origin, and carry-overs go into the new week's bank. Changes made mid-week (a new goal, a raised target, an item turned on) make their tasks in the open weeks. The week read says what closing will do to each task and which ones to ask "Still matter?" about. Nothing is put on a day yet: the planner (#10) fills the hook this slice leaves.

Ten tasks. **One PR** in the API, `week-turnover` (closes #9), split into two if it gets long: tasks 1–5 (opening and closing), then 6–10 (changes, reads, contract).

## The contract

New:

| Operation | Route | Body | Returns |
| --- | --- | --- | --- |
| `wrapUpWeek` | `POST /api/weeks/{week}/wrap-up` | | the new current week (`Week`) |
| `getUpcoming` | `GET /api/tasks/upcoming` | | `{ "tasks": [...] }`: open, with a later due date and no row yet, by due date |
| `answerStillMatters` | `POST /api/tasks/{id}/still-matters` | `{ "answer": "keep" }`, `{ "answer": "schedule", "week", "day" }` or `{ "answer": "drop" }` | the task |

Changed:

- **`Task` gains two fields**, filled on every read and write that returns a task:
  - `atClose`: `"carriesOver"`, `"ends"` or `null`. What closing its week would do if it's still unfinished. `null` when it's done, closed or set aside. The wrap-up sheet reads this; the phone holds no rules.
  - `stillMatters`: `true` when the task should be asked "Still matter?": added by hand or a fixed-day recurring task, open, and rolled over twice since it was last answered.
- **`Week`**: `isCurrent` and `nextWeekOpen` now follow `closedThroughWeek`, so after a wrap-up the current week is next week even on Sunday night.
- **Every route that asks for the day first brings the weeks up to date** (below). It needs no new header or body.

`checkOffTask`, `uncheckTask`, `placeTask`, `moveTaskToBank`, `swapTasks` and `dropTask` keep their bodies (shared decision 14).

## Architecture decisions

- **The clock is a dependency.** `app/time_zone.py` gains `Now` (the moment, in the phone's zone) beside `Today`. Rules take the moment as an argument and never read the clock. Tests pin it in `conftest.py`, to a Wednesday at noon unless a test sets it. Today the tests read the real date, so a run on a Sunday evening would open a week mid-test. Pinning it is task 1.
- **One step brings the weeks up to date: `catch_up(connection, user_id, now)`** in `app/turnover/rules.py`. The `Today` dependency calls it in its own write transaction, audited `close week` or `open week`, before the route runs. It takes the user lock and reads the two markers. When nothing is due, it returns without writing, so a read costs one locked select. The order:
  1. Close every week that has rows, up to the one before the current week, oldest first. Weeks with no rows are skipped.
  2. Open the current week if it isn't open.
  3. Open next week if it's Sunday at 6 p.m. or later.
- **`closed_through_week` is a column on `users`** (one migration, nullable). `open_weeks` and `target_week` take it, so the current week is the later of the week after it and the phone's week. This finishes what `app/weeks.py` left open.
- **What's due is pure code:** `app/turnover/due.py`, with no database, takes a goal's target and start, or an item's schedule and `startsOn`, and gives the tasks one week should have, as `(period_start, number)` pairs:
  - a goal's sessions: its target's sessions for the week. In the week of its start, or when it comes back midweek, at most one per day left, today included;
  - a fixed weekly item: its weekday, once on or after `startsOn`;
  - a fixed monthly item: its day of month, if it falls in the week;
  - a flexible item: its `times` for the period that starts in this week. A two-week period is anchored on `startsOn`'s week. A month is the weeks whose Monday falls in it. The short-first-week cap applies here too.

  Generated tasks are inserted `on conflict do nothing` against the existing unique keys, so making them twice makes nothing new. The spec forbids hitting a unique index as the normal path, so the code reads what exists first, and the conflict clause is only the backstop for two writers.
- **A generated task's title** is the goal's label or the item's name when it's made. Later renames don't change tasks already made.
- **Closing, by origin** (data model, "How a week ends"):
  - by hand: rolls over;
  - fixed-day recurring: rolls over;
  - weekly target: lapses;
  - flexible recurring: lapses at the end of its period, and rolls over inside it;
  - set aside: a generated task closes as lapsed with its row left set aside; one added by hand waits.

  A rolled-over task's new row goes in the bank (`planned_day` null, not placed by hand).
- **`atClose` is worked out in SQL**, in the task view query, from the origin, the item's schedule and the period start. The closing code and the read use the same rule from `due.py`. A test checks that they agree on every case.
- **"Still matter?"** counts the task's rows with outcome `rolled_over` whose week is after `still_matters_answered_on` (the column `tasks` already has). Keep and schedule set that column to today. Schedule also places the task by hand, as `placeTask` does. Drop is `dropTask`'s rule. A flexible item carrying inside its period is never asked.
- **The planner's hook:** `place_new_work(connection, user_id, task_ids, first_day)` in `app/planner.py`. Opening calls it with the week's new tasks and the first day it may use; each change in task 6 calls it with its new tasks and tomorrow. In this slice it does nothing, so everything stays in the bank. #10 fills it in.
- **Changes act on every open week** (spec): a goal created, resumed, reopened or gone again; an item created or turned on. Each gets the current week's tasks if it has none, and next week's too once next week is open.
  - **A target raised** adds sessions to the week the change takes effect in (`target_week`).
  - **A target lowered** removes the open sessions that are now extra: the last in the week first, so the bank before any day, and then the latest day (Jan, 2026-11-19). Removing one soft-deletes it, so it isn't made again. A session done or set aside is never removed.
- **An item edit takes effect from its next period.** Tasks already made for this period stay as they are, on their days. This keeps an edit from moving things on Today (assumed below).
- **Late unchecks** reuse the closing rule. `uncheck` asks the same function what the closed week would have done, so a recurring task gets its proper ending. This finishes `tasks-week` settled 3.

## Dependency graph

```
clock + closed_through_week (1)
    └── due.py (2)
          └── opening a week + catch_up (3)
                └── closing a week, late uncheck (4)
                      └── wrapUpWeek (5)
                            ├── changes act on open weeks: goals, targets (6)
                            │      └── items (7)
                            ├── atClose + stillMatters + getUpcoming (8)
                            │      └── answerStillMatters (9)
                            └── docs, openapi.json, front-end types (10)
```

## Task list

- [x] Task 1: Pin the clock, and add closed_through_week
- [ ] Task 2: What a week is due
- [ ] Task 3: Open a week
- [ ] Task 4: Close a week
- [ ] Task 5: Wrap up the week by hand

Checkpoint after task 5: weeks open and close; the four checks pass.

- [ ] Task 6: Goals and targets act on the open weeks
- [ ] Task 7: Recurring items act on the open weeks
- [ ] Task 8: What closing will do, "Still matter?", and the upcoming list
- [ ] Task 9: Answer "Still matter?"
- [ ] Task 10: Docs, the contract and the front end's types

Checkpoint after task 10: the slice is done, and the front end's mock compiles against the new types.

## Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Pinning the clock breaks tests written against the real date | Med | Task 1 alone, before any behaviour changes. The tests' `today()` helper reads the pinned date. |
| `catch_up` on every request slows reads | Low | It's one locked select when nothing is due. A test counts the queries. |
| Two requests open the same week together | High | The user lock, plus the unique keys as a backstop. A lock test, as in `tests/test_user_lock.py`. |
| The closing rule and `atClose` drift apart | Med | One function in `due.py` decides both, and a table test runs every origin through both. |
| Flexible periods across month boundaries get the wrong week | Med | Example tests on real calendars: November–December 2026, a two-week period anchored mid-month, and a 5-week month. |
| The task is too big to review | Med | Split the PR after task 5 if the diff passes about 1,500 lines. |

## Decisions (Jan, 2026-11-19)

- Lowering a target removes the last session in the week.
- "Still matter?" counts two rollovers since the last answer. Skipped weeks add no row.
- A short first week reads against the sessions it got ("1 of 2").
- The app places only recurring work; carry-overs go to the bank (ADR-013).

## Assumed, for review with this plan

1. **An item edit takes effect from its next period.** Tasks already made stay, so editing Tuesday to Thursday mid-week leaves this week's task where it is.
2. **Removing an extra session soft-deletes it** rather than closing it as lapsed, so it leaves no miss in history.
3. **The short-first-week cap applies to a new flexible item too:** "3 times a week" added on Saturday makes two this week.
4. **`atClose` and `stillMatters` go on `Task`** rather than in a separate list on `Week`, so every task the phone holds carries them, and a check-off's response stays whole.
5. **`answerStillMatters` is one route with three answers.** Drop goes through the same rule as `dropTask`, which stays.
