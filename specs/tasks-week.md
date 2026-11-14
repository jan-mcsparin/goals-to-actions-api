# Spec: Tasks and the week

Status: draft 2026-11-13; finalised when its plan is written. Issue: [#7](https://github.com/jan-mcsparin/goals-to-actions-api/issues/7). Module `tasks-week` in the [map](README.md). Depends on `goals-targets`.

## Objective

The centre of the app: tasks, the record of each week a task is in play, and everything the person does on Today and Week. After this slice a person can add tasks by hand, put them on days, check them off and move them about, and Today, Week and the bank are read from real data. Nothing is generated or drafted yet; that is the next three slices.

This is the largest slice. If its plan runs past about ten tasks it is split in two: reading and adding first, then the moves.

References: [`data-model.md`](../../docs/data-model.md#tasks) (tasks, task_weeks, how a week ends), [ADR-006](../../docs/adr/0006-task-weeks.md), [`product-rules.md`](../../docs/product-rules.md#planning).

## Scope

**In:**

- The `tasks` table, with every column in the data model, including the ones only generated tasks use (recurring item, period start, number), so later slices add no columns. The link to `recurring_items` is added by that slice.
- The `task_weeks` table: task, week, planned day, placed by hand, outcome.
- Reads: `getDay` (any day; Today is a day), `getWeek`, `getBank`. Each task comes with what the screen shows: its goal's label, its time, how many times it has carried over.
- Writes, all of them things the person did:
  - `addTask`: to the bank or straight onto a day; with or without a goal; a one-off goal's step is a task with that goal.
  - `updateTask`: title, due date, time of day.
  - `checkOffTask` (with the moment and day the phone saw, and an optional value logged), `uncheckTask`.
  - `moveTaskToBank`, `placeTask` (onto a day, marked placed by hand; pulling a bank task to today is this), `swapTasks`.
  - `dropTask`.
- Finishing what `goals-targets` left: pausing a goal sets its unfinished tasks aside for the week, and resuming returns its open tasks to this week's bank. A goal's read gains this week's progress, by count or by amount, and a one-off goal's "Step 3 of 6".
- The rules: a task has a goal or a recurring item or neither; at most one row per task per week and one row in play; a planned day inside its row's week; a task's state and its rows agree, changed in one transaction.
- ADR-007's remaining check: how `numeric` (the value logged) is typed.

**Out (later):**

- Tasks made from targets and recurring items; rollover and lapse; the upcoming list; "Still matter?" (`week-turnover`).
- The app placing anything on a day (`planner`).
- Delete a task (`delete`).
- Ordering tasks within a day by hand; partial credit; a task serving two goals.

## Testing strategy

As shared, plus: each row of the data model's "on screen / in the data" table has a test; each rule above has a test that tries to break it in the database; a check-off at 12:30 a.m. counts for the day the phone sent; check-off then uncheck leaves the task as it was; pausing and resuming a goal with tasks in the bank, on days and placed by hand.

## Boundaries

As shared. **Never:** change a task's planned day except in a route the person called; commit a transaction that leaves a task's state and its rows disagreeing.

## Success criteria

- [ ] A person can add, place, check off, uncheck, move, swap and drop tasks, and the three reads show the result.
- [ ] Every rule above is held by the database or the route, with a test.
- [ ] Pause and resume set aside and return tasks.
- [ ] Progress against a weekly target reads correctly for count and amount.
- [ ] ADR-007 records how `numeric` is typed.
- [ ] The front end's types are regenerated from the new schema and its mock client compiles against them.
- [ ] The four checks pass.

## Open questions

1. **A one-off goal's steps and the week.** `flows.md` lists as open when an undated step enters a week. For this slice, a step with no date waits with no row until the person puts it somewhere. Is that right until the planner decides?
2. **Adding a task dated in a later week:** it waits on the upcoming list with no row. Can the person also place it on a day in that week? The model allows it; the app doesn't offer it yet. I'd leave it out.
3. **What exactly is a swap?** Trading a planned task with one from the bank, or two planned tasks trading days, or both. Confirmed against the front end in the plan.
4. **Which week does a write belong to when the phone and the server disagree about the day** (a queued check-off sent after midnight)? The assumed convention is that the phone's stated day wins for a check-off.
