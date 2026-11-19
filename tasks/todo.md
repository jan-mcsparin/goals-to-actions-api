# Tasks: Tasks and the week (#7)

Plan: [`plan.md`](plan.md). Spec: [`../specs/tasks-week.md`](../specs/tasks-week.md).

Every task: write the tests first, run the four checks (`uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run pytest`), then one commit.

# PR A: `tasks-week-read-add` (part of #7)

### Task 1: The tasks table

**Description:** The migration: the shared columns; title, origin, goal, recurring item (no foreign key yet), state, due date, time-of-day kind and time, value logged (`numeric`), completed at and on, period start, number, still matters answered on; both triggers. Queries in `db/queries/tasks.sql`.

**Acceptance criteria:**
- [x] The database refuses:
  - a task with both a goal and a recurring item
  - another owner's goal
  - a weekly-target task with no goal
  - an unknown origin or state
  - a blank title
  - a time-of-day kind with no time, or a time with no kind
- [x] A generated task can't be made twice for the same goal or item, period and number, even after the first is deleted.
- [x] Up, rollback, up leaves `db/schema.sql` unchanged.

**Verify:** `uv run pytest tests/test_tasks_table.py`.

**Dependencies:** none.

**Files:** `db/migrations/<ts>_tasks.sql`, `db/queries/tasks.sql`, `db/schema.sql`, `app/db/`, `tests/test_tasks_table.py`.

### Task 2: The task_weeks table, and state agreeing with rows

**Description:** The migration: the shared columns; task, week, planned day, placed by hand, outcome; the checks; the deferred constraint trigger tying a task's state to its rows. Queries in `db/queries/task_weeks.sql`.

**Acceptance criteria:**
- [x] The database refuses:
  - a week that isn't a Monday
  - a planned day outside its week
  - two rows for one task in one week
  - two rows in play for one task
  - another owner's task
  - an unknown outcome
- [x] At commit, it also refuses a done, dropped or lapsed task with a row in play, and a done task whose last row isn't done. Within the transaction, both are allowed.
- [x] Up, rollback, up leaves `db/schema.sql` unchanged.

**Verify:** `uv run pytest tests/test_task_weeks_table.py`.

**Dependencies:** 1.

**Files:** `db/migrations/<ts>_task_weeks.sql`, `db/queries/task_weeks.sql`, `db/schema.sql`, `app/db/`, `tests/test_task_weeks_table.py`.

### Task 3: Add a task, and the week read

**Description:** `PUT /api/tasks/{id}` (`addTask`) and `GET /api/weeks/{week}` (`getWeek`), plus `current_week` in `app/weeks.py`. The week read starts with `tasks`, `isCurrent` and `nextWeekOpen`; `goals` and its progress come in task 6.

**Acceptance criteria:**
- [x] A task added with no day goes to the current week's bank; with a day this week, onto that day, placed by hand; with a goal, under the goal.
- [x] Where a task lands:
  - a due date in an open next week: that week's bank
  - a due date in a later week that isn't open: no row
  - a one-off step with no date: no row
  - a past day, or today before the current week: the current week's bank
- [x] The rest:
  - sent twice, it returns the task as it is
  - another owner's goal is a 404
  - a goal that isn't active is a 409
  - `getWeek` shows each task's goal label and `carriedOver`
  - a week that isn't a Monday is a 422

**Verify:** `uv run pytest tests/test_tasks.py tests/test_week_read.py`.

**Dependencies:** 2.

**Files:** `app/tasks/{models,routes,rules,week}.py`, `app/weeks.py`, `app/main.py`, `db/queries/*.sql`, `tests/test_tasks.py`, `tests/test_week_read.py`, `tests/test_user_lock.py`, `openapi.json`.

### Task 4: Edit a task

**Description:** `PATCH /api/tasks/{id}` (`updateTask`): title, due date and time of day, sent whole.

**Acceptance criteria:**
- [x] The edit is saved, and the task stays where it is.
- [x] Another owner's task is a 404, and a blank title is a 422.

**Verify:** `uv run pytest tests/test_tasks.py`.

**Dependencies:** 3.

**Files:** `app/tasks/*`, `db/queries/tasks.sql`, `tests/test_tasks.py`, `openapi.json`.

### Task 5: Check off and uncheck

**Description:** `POST /api/tasks/{id}/check-off` and `/uncheck`, on the open weeks. Weeks that have already closed come in task 11.

**Acceptance criteria:**
- [x] Checking off:
  - marks the row and the task done with the moment, the day and the value
  - counts a check-off at 12:30 a.m. for the day the phone sent
  - on a task with no row, makes a done row on that day, in that day's week
  - on a next-week row, is a 409
  - on a dropped task, is a 409
- [x] Unchecking:
  - after a check-off, leaves the task and its row as they were
  - on a waiting step checked off from the goal's page, leaves it in play on that day (one rule)
  - clears the value logged
- [x] Each sent twice changes nothing more.

**Verify:** `uv run pytest tests/test_check_off.py`.

**Dependencies:** 3.

**Files:** `app/tasks/*`, `db/queries/*.sql`, `tests/test_check_off.py`, `openapi.json`.

### Task 6: This week's progress, and a one-off goal's steps

**Description:** `weekProgress` on goal reads; a one-off goal's `progress` from its steps; `steps` on the goal's page; `goals` on the week read.

**Acceptance criteria:**
- [x] Count progress is the tasks done in this week's rows, out of sessions. Amount progress is the sum of the values logged, out of the amount.
- [x] A task counts for the week of the row it was done in.
- [x] A one-off goal reads "3 of 6" with dropped steps left out, and its page lists its steps.
- [x] `getWeek.goals` lists the active building goals with a target that week, with progress.
- [x] One query for the whole list's progress.

**Verify:** `uv run pytest tests/test_goal_reads.py tests/test_week_read.py`.

**Dependencies:** 5.

**Files:** `app/goals/models.py`, `app/goals/routes.py`, `app/milestones/{models,page}.py`, `app/tasks/week.py`, `db/queries/*.sql`, tests, `openapi.json`.

## Checkpoint A

- [x] The four checks pass.
- [x] PR A opened (part of #7).

# PR B: `tasks-week-moves` (closes #7)

### Task 7: Place on a day, and back to the bank

**Description:** `POST /api/tasks/{id}/place` (`week`, `day`) and `/bank` (`week`).

**Acceptance criteria:**
- [x] Placing sets the day and marks the row placed by hand, and works on next week's rows. Back to the bank clears the day and the placed-by-hand mark.
- [x] Each is a 409 when:
  - the task's row in play is in another week than the one named
  - the day is a past day
  - the day is outside the row's week, which covers today before the current week
  - the task isn't in play
- [x] Each sent twice changes nothing more.

**Verify:** `uv run pytest tests/test_task_moves.py`.

**Dependencies:** 3.

**Files:** `app/tasks/*`, `db/queries/task_weeks.sql`, `tests/test_task_moves.py`, `openapi.json`.

### Task 8: Swap

**Description:** `POST /api/tasks/{id}/swap` (`week`, `bankTaskId`, `day`). The task named in the route goes to the bank, and the bank task goes onto the day.

**Acceptance criteria:**
- [x] Both tasks change in one transaction. Both are checked before either changes.
- [x] It's a 409 when either task's row is in another week than the one named, or when the day isn't allowed. It's a 404 when either task belongs to another owner.
- [x] Sent twice, it changes nothing more.

**Verify:** `uv run pytest tests/test_task_moves.py`.

**Dependencies:** 7.

**Files:** `app/tasks/*`, `tests/test_task_moves.py`, `openapi.json`.

### Task 9: Drop

**Description:** `POST /api/tasks/{id}/drop`: the task becomes dropped, and its row in play closes as dropped.

**Acceptance criteria:**
- [x] A dropped task leaves the week read. A done task can't be dropped (409).
- [x] Sent twice, it changes nothing more.

**Verify:** `uv run pytest tests/test_task_moves.py`.

**Dependencies:** 7.

**Files:** `app/tasks/*`, `tests/test_task_moves.py`, `openapi.json`.

### Task 10: Pausing sets tasks aside; coming back returns them

**Description:** `change_status` in `app/goals/rules.py` calls new task rules.

**Acceptance criteria:**
- [x] Pause, end and reach set the goal's unfinished rows aside in every open week: on days, placed by hand, and in the bank. They keep their day.
- [x] Resume, reopen and go again bring them back:
  - a set-aside row whose week is open returns to that week's bank
  - a task added by hand whose week has closed gets a row in the current week's bank
- [x] Sent twice, each changes nothing more.

**Verify:** `uv run pytest tests/test_goal_tasks.py`.

**Dependencies:** 7.

**Files:** `app/goals/rules.py`, `app/tasks/rules.py`, `db/queries/task_weeks.sql`, `tests/test_goal_tasks.py`.

### Task 11: Check-offs and unchecks that arrive after their week closed

**Description:** A late check-off, and a late uncheck, in weeks that have closed. Tests make the closed rows directly in SQL.

**Acceptance criteria:**
- [ ] A late check-off:
  - on a lapsed task, turns the task and that row to done
  - on a task that rolled over, lands on its row in the new week
  - keeps the phone's stated day
- [ ] A late uncheck gives the task the ending its week would have given it: rolled over into the current week's bank (added by hand) or lapsed (weekly target).

**Verify:** `uv run pytest tests/test_check_off.py`.

**Dependencies:** 5, 10.

**Files:** `app/tasks/rules.py`, `db/queries/task_weeks.sql`, `tests/test_check_off.py`.

### Task 12: Docs, ADR-007 and the front end's types

**Description:** Record what was built, and regenerate the front end's types.

**Acceptance criteria:**
- [ ] ADR-007 says how `numeric` is typed.
- [ ] `data-model.md` and `flows.md` match what was built, including uncheck's single rule.
- [ ] `specs/tasks-week.md` is final, with its open questions answered and its success criteria ticked.
- [ ] CLAUDE.md's structure names `tasks/`.
- [ ] The front end's types are regenerated (`npm run api:types`), and its mock client compiles (`npm run build`, `npm test`), in a front-end PR.

**Verify:** the four checks; `npm run build` and `npm test` in `web-frontend/`.

**Dependencies:** 1–11.

**Files:** `../docs/adr/0007-*.md`, `../docs/data-model.md`, `specs/tasks-week.md`, `specs/README.md`, `CLAUDE.md`, `web-frontend/src/api/openapi.ts`.

## Checkpoint B

- [ ] Every spec success criterion is met.
- [ ] The four checks pass.
- [ ] PR B opened (closes #7), with the docs and front-end PRs alongside.
