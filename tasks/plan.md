# Implementation Plan: Tasks and the week (#7)

Spec: [`../specs/tasks-week.md`](../specs/tasks-week.md). Tasks: [`todo.md`](todo.md).

## Overview

The `tasks` and `task_weeks` tables, the week read, and every write a person makes on Today, Week, the bank and a one-off goal's page. Pausing and coming back finally move a goal's tasks, and goal reads gain this week's progress and a one-off goal's steps. Nothing is generated or drafted yet.

The spec asks for a split past about ten tasks. This plan has twelve, so it ships as **two PRs**, as the spec suggests:

- **PR A, `tasks-week-read-add`** (part of #7): the tables, `getWeek`, `addTask`, `updateTask`, check off and uncheck, progress and steps.
- **PR B, `tasks-week-moves`** (closes #7): place, bank, swap, drop, setting aside and returning, docs, and the front end's types.

## The contract

| Operation | Route | Body | Returns |
| --- | --- | --- | --- |
| `getWeek` | `GET /api/weeks/{week}` | | the week (below); 422 if `week` isn't a Monday |
| `addTask` | `PUT /api/tasks/{id}` | `title`, `goalId?`, `dueDate?`, `timeOfDay?`, `day?` | the task |
| `updateTask` | `PATCH /api/tasks/{id}` | `title`, `dueDate`, `timeOfDay`, sent whole | the task |
| `checkOffTask` | `POST /api/tasks/{id}/check-off` | `completedAt`, `completedOn`, `valueLogged?` | the task |
| `uncheckTask` | `POST /api/tasks/{id}/uncheck` | | the task |
| `placeTask` | `POST /api/tasks/{id}/place` | `week`, `day` | the task |
| `moveTaskToBank` | `POST /api/tasks/{id}/bank` | `week` | the task |
| `swapTasks` | `POST /api/tasks/{id}/swap` | `week`, `bankTaskId`, `day`; `{id}` goes to the bank | both tasks |
| `dropTask` | `POST /api/tasks/{id}/drop` | | the task |

**The week:** `week`, `isCurrent`, `nextWeekOpen`, `tasks`, `goals`.

- `tasks`: the week's rows with no outcome or done; set-aside rows aren't shown. Each task has `id`, `title`, `origin`, `state`, `goalId`, `goalLabel`, `recurringItemId`, `dueDate`, `timeOfDay` (`kind`, `time`), `valueLogged`, `completedAt`, `completedOn`, `plannedDay` (null in the bank), `placedByHand`, and `carriedOver` (its rolled-over rows).
- `goals`: every active building goal with a target that week, with `id`, `label`, `target`, `progress` (`done` and `of`, by count or by amount). This is what Week's bars need.

**The task** (every write returns it) is the same object, plus `week`: the week of its row in play or of its done row, or null while it waits.

**`addTask`'s `day`** is the phone's end result, in place of the mock's `onToday`. With no day the task goes to the bank of the current week, or of its due date's week when that week is open. A due date in a later week that isn't open yet leaves the task waiting with no row (the upcoming list). A one-off goal's step with no date waits with no row too. A day that's no longer allowed (a past day, or today when today is before the current week) puts the task in the current week's bank.

**Goal reads gain:**

- `weekProgress` on every goal: a building goal's `done` and `of` this week, by count or by amount; null for other types.
- A one-off goal's `progress` counts steps: `hit` is the steps done, `of` is the steps not dropped.
- The goal's page gains `steps` for a one-off goal: its tasks, done and not done, in the order added.

## Architecture decisions

- **`tasks` has every column the data model lists**, including `recurring_item_id`, `period_start` and `number`. `recurring_items` adds the foreign key. The unique rule for generated tasks is a plain unique index (no `where deleted_at is null`), so it counts deleted rows.
- **A task points at `goals (id, user_id)`; a `task_weeks` row points at `tasks (id, user_id)`.** The owner rides on every foreign key, as in earlier slices.
- **Rules the database holds:**
  - goal or item or neither, never both
  - a week is a Monday
  - a planned day falls inside its row's week
  - one row per task per week, and one with no outcome (a partial unique index)
  - the time of day's kind and time come together
- **"A task's state and its rows agree" is a deferred constraint trigger** on both tables, checked at commit:
  - an open task has at most one row in play
  - done, dropped and lapsed tasks have none
  - a done task's last row is done

  A route that gets it wrong fails its own test, not quietly.
- **The current week is the phone's week** for now. `week-turnover` adds `closed_through_week` and moves this to `app/weeks.py` (`current_week`), the one function every task rule calls. Next week is open when `planned_through_week` is after it.
- **`numeric` is `decimal.Decimal`** in sqlc's generated code. That's how `weekly_targets.amount` already works. The API sends the value as a JSON number and turns it back into a Decimal on the way in, as `WeeklyTargetInput` does. This is recorded in ADR-007.
- **`app/tasks/`** holds routes, models and rules; `app/tasks/week.py` builds the week read. Goal progress is one query per read, not per goal.
- **No new dependency.**

## Dependency graph

```
1 tasks ──► 2 task_weeks (+ agreement trigger)
                 │
                 ▼
            3 addTask + getWeek ──► 4 updateTask
                 │
                 ▼
            5 check off / uncheck ──► 6 progress + steps ──► [PR A]
                 │
                 ▼
            7 place + bank ──► 8 swap ──► 9 drop
                 │
                 ▼
            10 set aside + return ──► 11 closed-week check-off and uncheck ──► 12 docs, ADR-007, front-end types ──► [PR B]
```

## Task list

See [`todo.md`](todo.md).

PR A, `tasks-week-read-add`:

- [x] 1: The tasks table
- [x] 2: The task_weeks table, and state agreeing with rows
- [x] 3: Add a task, and the week read
- [x] 4: Edit a task
- [x] 5: Check off and uncheck
- [x] 6: This week's progress, and a one-off goal's steps
- [x] **Checkpoint A:** tasks can be added, read, edited, checked off; checks pass; PR A opened

PR B, `tasks-week-moves`:

- [x] 7: Place on a day, and back to the bank
- [x] 8: Swap
- [x] 9: Drop
- [x] 10: Pausing sets tasks aside; coming back returns them
- [x] 11: Check-offs and unchecks that arrive after their week closed
- [ ] 12: Docs, ADR-007 and the front end's types
- [ ] **Checkpoint B:** every spec criterion met; checks pass; PR B opened

## Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Nothing closes a week until slice 7, so the closed-week cases can't happen through the API yet | Medium | Tests make closed rows directly in SQL. Slice 7 then reuses the same endings. |
| The agreement trigger rejects a valid step between two writes in one transaction | Medium | It is deferred to commit; each write's tests commit through the trigger. |
| `getWeek` differs from the mock's `WeekPlan` (`weekOf`, `status`, `rolloverCount`, `onToday`) | Low | The front end keeps its hand-written types until #42 switches the screens. Only regenerating and compiling is in scope here. |
| PR B changes goal status writes from slice 3 | Low | The existing status tests stay; new ones cover tasks. |

## Decisions (approved 2026-11-18)

1. **Uncheck has one rule** (settled with Jan 2026-11-18): the task's row goes back in play as it was. A waiting step checked off on the goal's page made a row on the day it was done, so unchecking it leaves it on that day rather than waiting. No new column; `data-model.md`'s "Unchecking removes the row" changes.
2. **A swap trades a task on a day for one from the bank.** The day's task goes to the bank and the bank task takes its day, as the front end's `swapTask` does today (spec open question 2). Two day tasks trading days is out.
3. **No placing a task in a later week that isn't open** (spec open question 1, the spec's own recommendation). It waits on the upcoming list.
4. **`addTask` takes `day`, not `onToday`,** so a queued add states where it ends up. The phone sends today's date.
5. **Writes return the task, not the week.** The phone fetches the week again once its queue is empty (ADR-010). `swapTasks` returns both tasks.
6. **Uncheck clears the value logged** along with the completion, as the mock does.
