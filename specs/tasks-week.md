# Spec: Tasks and the week

Status: built 2026-11-18, in two PRs (#33, and the moves). Issue: [#7](https://github.com/jan-mcsparin/goals-to-actions-api/issues/7). Module `tasks-week` in the [map](README.md). Depends on `goals-targets`.

## Objective

The centre of the app: tasks, the record of each week a task is in play, and everything the person does on Today and Week. After this slice a person can add tasks by hand, put them on days, check them off and move them about, and Today, Week and the bank are drawn from real data. Nothing is generated or drafted yet; that is the next three slices.

This is the largest slice. If its plan runs past about ten tasks it is split in two: reading and adding first, then the moves.

References: [`data-model.md`](../../docs/data-model.md#tasks) (tasks, task_weeks, how a week ends), [ADR-006](../../docs/adr/0006-task-weeks.md), [ADR-010](../../docs/adr/0010-week-document-and-replayed-queue.md), [`product-rules.md`](../../docs/product-rules.md#planning).

## Scope

**In:**

- The `tasks` table, with every column in the data model, including the ones only generated tasks use (recurring item, period start, number), so later slices add no columns. The link to `recurring_items` is added by that slice.
- The `task_weeks` table: task, week, planned day, placed by hand, outcome.
- One plan read, `getWeek`, which takes a week (ADR-010). It returns every task in that week, on a day, in the bank or done, each with what the screen shows: its goal's label, its time, how many times it has carried over. It also says whether the week is the current one and whether next week is open. The phone stores it and draws Today, any day and the bank from it; there is no `getDay` or `getBank`.
- Two weeks can be open at once (ADR-009): the current week and, from Sunday evening, the next. Nothing opens a second week until `week-turnover`, but the read and the writes below are written for it from the start.
- **The queueable writes** (ADR-010) are `addTask`, `checkOffTask`, `uncheckTask`, `placeTask`, `moveTaskToBank` and `swapTasks`. Three rules hold for them:
  - each states its end result, so sending it twice changes nothing more. `swapTasks` names the task going to the bank, the task being placed, and the day;
  - `placeTask`, `moveTaskToBank` and `swapTasks` name the week they were made in, and are refused (409) if the task's row in play is in another week;
  - `addTask` is never refused over where the task goes. A day that is no longer allowed (a past day, or today when today is before the current week) saves it in the current week's bank.
- Writes, all of them things the person did:
  - `addTask`: to the bank or straight onto a day; with or without a goal; a one-off goal's step is a task with that goal. A task due in a week that is already open goes into that week's bank.
  - When today is before the current week (after a wrap-up, or a flight west), `placeTask` onto today is refused (409): a planned day must be inside its row's week.
  - `updateTask`: title, due date, time of day.
  - `checkOffTask` (with the moment and day the phone saw, and an optional value logged), `uncheckTask`. A row in a week that isn't the current one yet can be moved but not checked off (409).
    - Checking off a task with no row (a one-off goal's waiting step, from the goal's page) makes a done row on the day the phone sent, in that day's week. Unchecking removes the row.
    - A check-off dated inside a week that has closed still counts. A lapsed task and its row turn to done; a task that rolled over is checked off on its row in the new week. The phone's stated day wins.
    - An uncheck of a task whose week has closed gives it the ending that week would have given it: rolled over into the current week's bank, or lapsed.
  - `moveTaskToBank`, `placeTask` (onto a day, marked placed by hand; pulling a bank task to today is this), `swapTasks`. None of them places on a day before today, or moves a fixed-day recurring task off its day (409); one that carried over is placed like any task.
  - `dropTask`.
- Finishing what `goals-targets` left:
  - pausing, ending or reaching a goal sets its unfinished tasks aside in every open week;
  - resume, reopen and go again return them: a task whose week is still open goes to that week's bank, and a task added by hand whose week has closed gets a row in the current week's bank;
  - a goal's read gains this week's progress, by count or by amount, and a one-off goal's "Step 3 of 6", which leaves dropped steps out of the total;
  - a task counts for the week of the row it was done in, not the date it was checked off.
- The unique rule for generated tasks (goal or item, period, number) counts deleted rows, so a deleted session is never made again.
- A task with a recurring item has the origin recurring item, but not the other way round: `delete` empties the link on a deleted item's done tasks.
- The rules: a task has a goal or a recurring item or neither; at most one row per task per week and one row in play; a planned day inside its row's week; a task's state and its rows agree, changed in one transaction.
- ADR-007's remaining check: how `numeric` (the value logged) is typed.

**Out (later):**

- Tasks made from targets and recurring items; rollover and lapse; the upcoming list; "Still matter?" (`week-turnover`).
- The app placing anything on a day (`planner`).
- Delete a task (`delete`).
- Ordering tasks within a day by hand; partial credit; a task serving two goals.

## Testing strategy

As shared, plus: each row of the data model's "on screen / in the data" table has a test; each rule above has a test that tries to break it in the database; a check-off at 12:30 a.m. counts for the day the phone sent; check-off then uncheck leaves the task as it was; pausing and resuming a goal with tasks in the bank, on days and placed by hand; the same for ending and reopening; a waiting step checked off and unchecked from the goal's page; a check-off dated in a closed week; adding onto today when today is before the current week, and onto a past day, both saved in the bank; an uncheck dated in a closed week; a plan edit naming a week the task has left.

## Boundaries

As shared. **Never:** change a task's planned day except in a route the person called; commit a transaction that leaves a task's state and its rows disagreeing.

## Success criteria

- [x] A person can add, place, check off, uncheck, move, swap and drop tasks, and the week read shows the result.
- [x] Each queueable write sent twice changes nothing more, and a plan edit aimed at a week the task has left is refused.
- [x] Every rule above is held by the database or the route, with a test. A task's state and its rows agreeing is a constraint trigger checked at commit.
- [x] Pause and resume set aside and return tasks; so do end and go again, reach and reopen.
- [x] Progress against a weekly target reads correctly for count and amount.
- [x] ADR-007 records how `numeric` is typed.
- [x] The front end's types are regenerated from the new schema and its mock client compiles against them.
- [x] The four checks pass.

## The contract, as built

| Operation | Route | Body | Returns |
| --- | --- | --- | --- |
| `getWeek` | `GET /api/weeks/{week}` | | the week; 422 if `week` isn't a Monday |
| `addTask` | `PUT /api/tasks/{id}` | `title`, `goalId?`, `dueDate?`, `timeOfDay?`, `day?` | the task |
| `updateTask` | `PATCH /api/tasks/{id}` | `title`, `dueDate`, `timeOfDay`; sent whole | the task |
| `checkOffTask` | `POST /api/tasks/{id}/check-off` | `completedAt`, `completedOn`, `valueLogged?` | the task |
| `uncheckTask` | `POST /api/tasks/{id}/uncheck` | | the task |
| `placeTask` | `POST /api/tasks/{id}/place` | `week`, `day` | the task |
| `moveTaskToBank` | `POST /api/tasks/{id}/bank` | `week` | the task |
| `swapTasks` | `POST /api/tasks/{id}/swap` | `week`, `bankTaskId`, `day`; `{id}` goes to the bank | `toBank` and `placed` |
| `dropTask` | `POST /api/tasks/{id}/drop` | | the task |

Every route but `updateTask` and `dropTask` needs `X-Time-Zone`.

- **The week:** `week`, `isCurrent`, `nextWeekOpen`, `tasks` (on a day, then the bank; rows with no outcome or done; set-aside rows aren't shown) and `goals` (each active building goal with a target that week: `id`, `label`, `weeklyTarget`, `progress`).
- **The task:**
  - `id`, `title`, `origin` (`byHand`, `weeklyTarget`, `recurringItem`), `state` (`open`, `done`, `dropped`, `lapsed`)
  - `goalId`, `goalLabel`, `recurringItemId`
  - `dueDate`, `timeOfDay` (`kind` `by` or `at`, `time` as `HH:MM`)
  - `valueLogged`, `completedAt`, `completedOn`
  - `week` and `plannedDay`: of its row in play, or of its done row. Both are empty while it waits or is set aside; `plannedDay` alone is empty in the bank.
  - `placedByHand`, and `carriedOver` (how many weeks it rolled over before)
- **Goal reads:**
  - `listGoals` and the goal's page gain `weekProgress` (`done` and `of`, by count or by amount; empty without a target this week).
  - A one-off goal's `progress` counts its steps, leaving dropped ones out.
  - The goal's page gains `steps`: a one-off goal's tasks, in the order added.

## Settled

1. **Adding a task dated in a later week that isn't open:** it waits on the upcoming list, with no row. Placing it on a day in that week isn't offered.
2. **A swap trades a task on a day for one from the bank.** The day's task goes to the bank and the bank task takes its day. Two day tasks trading days is out.
3. **Unchecking has one rule** (Jan, 2026-11-18): the row goes back in play as it was. A waiting step checked off on the goal's page made a row on the day it was done, so unchecking leaves it on that day. If the row's week has closed, the task gets the ending that week would have given it: a task added by hand rolls over into the current week's bank, and a generated one lapses. `recurring-items` adds the endings for recurring tasks.
4. **`addTask` takes `day`,** not an "on today" flag, so a queued add states where it ends up.
5. **Writes return the task.** The phone fetches the week again once its queue is empty (ADR-010).
6. **Unchecking clears the value logged.**
7. **A check-off from the bank leaves the task off the days.** It shows as done in the week read, with no `plannedDay`.
8. **Checking off is allowed on a task whose row is in a week before the current one.** Until `week-turnover` closes weeks, such a row is still in play.
9. **The current week is the phone's week** (`app/weeks.py`, `open_weeks`). `week-turnover` adds `closed_through_week`. "Today before the current week" is tested on the rule directly until then.
10. **Pausing sets aside rows in play from the current week on.** Coming back returns a set-aside row whose week is open to that week's bank. A task added by hand whose set-aside week has closed gets a row in the current week's bank.
11. **A one-off goal's step with no date waits with no row** until the person pulls it in or dates it (settled 2026-11-16).
12. **For a check-off, the phone's stated day wins,** even when its week has closed (settled 2026-11-16).
