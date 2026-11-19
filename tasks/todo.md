# Tasks: Week turnover (#9)

Plan: [`plan.md`](plan.md). Spec: [`../specs/week-turnover.md`](../specs/week-turnover.md).

Every task: write the tests first, run the four checks (`uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run pytest`), then one commit.

# PR: `week-turnover` (closes #9)

### Task 1: Pin the clock, and add closed_through_week

**Description:** `Now` in `app/time_zone.py`: the moment in the phone's zone, from a `clock` dependency that tests override. `Today` reads it. `conftest.py` pins the clock to Wednesday 18 Nov 2026 at noon, and a fixture lets a test set its own moment. The tests' `today()` helper reads the pinned date. A migration adds `users.closed_through_week`. `open_weeks` and `target_week` take it: the current week is the later of the week after it and the phone's week.

**Acceptance criteria:**
- [x] Every existing test passes against the pinned clock, with no test reading the real date.
- [x] `open_weeks` and `target_week` follow `closed_through_week`: after a wrap-up on Sunday night the current week is next week, and a flight west doesn't take it back.
- [x] Up, rollback, up leaves `db/schema.sql` unchanged.

**Verify:** `uv run pytest`; `tests/test_weeks.py` has the new cases.

**Dependencies:** none.

**Files:** `app/time_zone.py`, `app/weeks.py`, the callers of `open_weeks` and `target_week`, `db/migrations/<ts>_closed_through_week.sql`, `db/queries/users.sql`, `app/db/`, `db/schema.sql`, `tests/conftest.py`, `tests/test_goals.py` (its `today()`), `tests/test_weeks.py`.

**Scope:** M

### Task 2: What a week is due

**Description:** `app/turnover/due.py`, pure code: the `(period_start, number)` pairs a week is due for a goal's target and for each schedule kind, the short-first-week cap, and `ending(origin, schedule, period_start, week)`, which says rolls over or lapses. Nothing calls it yet.

**Acceptance criteria:**
- [x] Weekly on a weekday, from the first match on or after `startsOn`; monthly on the 1st and the 28th; flexible weekly, two-weekly anchored on `startsOn`, and monthly across November–December 2026 and a 5-week month.
- [x] A goal started on Saturday gets two sessions of three, and one started on Monday gets all three. A flexible item added on Saturday is capped the same way.
- [x] `ending` gives each row of the data model's "How a week ends" table, including a flexible task inside a longer period.

**Verify:** `uv run pytest tests/test_due.py`.

**Dependencies:** 1.

**Files:** `app/turnover/{__init__,due}.py`, `tests/test_due.py`.

**Scope:** S

### Task 3: Open a week

**Description:** `catch_up` in `app/turnover/rules.py`, called by the `Today` dependency in its own transaction. It opens the current week if it isn't open, and next week from 6 p.m. on Sunday. Opening makes the week's sessions and recurring tasks, and gives upcoming tasks now due a row in the bank. It sets `planned_through_week` and calls `place_new_work` (`app/planner.py`, which does nothing yet). Queries go in `db/queries/turnover.sql`.

**Acceptance criteria:**
- [ ] 5:59 p.m. on Sunday opens nothing; 6 p.m. opens next week with exactly what's due, and Sunday's rows are as they were. A first request on Wednesday opens the current week.
- [ ] Opening twice makes nothing new; a paused goal and an item turned off get nothing; the audit log says `open week`.
- [ ] Two requests together open the week once (a lock test). A read with nothing due writes nothing.

**Verify:** `uv run pytest tests/test_open_week.py tests/test_user_lock.py`.

**Dependencies:** 2.

**Files:** `app/turnover/rules.py`, `app/planner.py`, `app/time_zone.py`, `db/queries/turnover.sql`, `app/db/`, `tests/test_open_week.py`, `tests/test_user_lock.py`.

**Scope:** M

### Task 4: Close a week

**Description:** `catch_up` closes the weeks before the current one that have rows, oldest first, before it opens anything. Each unfinished row gets its ending from `due.ending`; set-aside rows follow the data model. Carry-overs get a row in the next open week's bank. It sets `closed_through_week`. `uncheck` asks the same rule for a row in a closed week, so a recurring task gets its proper ending.

**Acceptance criteria:**
- [ ] Each row of "How a week ends" closes as the data model says, and a week of 1 of 3 is followed by a week of 3, not 5.
- [ ] Opened on Sunday evening and closed on Monday, the carry-overs arrive in the bank then. Never opened on Sunday, one request on Monday closes, then opens. Three weeks away: the weeks with rows close in order, no rows are made for the empty ones, and a hand-added task carries over once.
- [ ] A check-off sent after Monday's close, dated Sunday, is done, not lapsed. A late uncheck of a fixed-day task rolls it over; of a flexible one inside its period, carries it. The audit log says `close week`.

**Verify:** `uv run pytest tests/test_close_week.py tests/test_check_off.py`.

**Dependencies:** 3.

**Files:** `app/turnover/rules.py`, `app/tasks/rules.py`, `db/queries/turnover.sql`, `app/db/`, `tests/test_close_week.py`, `tests/test_check_off.py`.

**Scope:** M

### Task 5: Wrap up the week by hand

**Description:** `wrapUpWeek`, `POST /api/weeks/{week}/wrap-up`, in `app/turnover/routes.py`. The same close as Monday's, run once next week is open. Returns the new current week.

**Acceptance criteria:**
- [ ] Wrapped up on Sunday evening, next week becomes the current week: its tasks can be checked off, and a task added to "today" goes to its bank.
- [ ] Before next week is open it's a 409, and so is a week after the current one. Sent twice, the second finds the week closed and returns the current week unchanged. The audit log says `wrap up week`.
- [ ] Monday's close after a wrap-up finds nothing to do.

**Verify:** `uv run pytest tests/test_wrap_up.py`.

**Dependencies:** 4.

**Files:** `app/turnover/{routes,rules}.py`, `app/main.py`, `tests/test_wrap_up.py`.

**Scope:** S

## Checkpoint: weeks open and close
- [ ] The four checks pass.
- [ ] Jan reviews the opening and closing tests before the rest is built.

### Task 6: Goals and targets act on the open weeks

**Description:** A goal created, resumed, reopened or gone again gets each open week's sessions if that week has none, with the short-first-week cap. A raised target adds sessions in the week it takes effect. A lowered one soft-deletes the extra open sessions, last in the week first: the bank before any day, then the latest day. New tasks go through `place_new_work`.

**Acceptance criteria:**
- [ ] A goal made on Saturday has two sessions in the bank; one made on Sunday evening also gets next week's full target.
- [ ] Raising 3 to 4 adds one session; lowering 3 to 2 removes the last open one, never a done or set-aside one. A target changed on Sunday evening leaves this week as it was.
- [ ] A goal paused in one week and resumed in a later one gets that week's sessions, and the old ones stay closed with no miss recorded.

**Verify:** `uv run pytest tests/test_goal_tasks.py tests/test_goals.py tests/test_goal_status.py`.

**Dependencies:** 5.

**Files:** `app/goals/rules.py`, `app/turnover/rules.py`, `db/queries/turnover.sql`, `app/db/`, `tests/test_goal_tasks.py`.

**Scope:** M

### Task 7: Recurring items act on the open weeks

**Description:** An item created or turned on gets its tasks for each open week if it has none. An edit makes nothing and moves nothing; it takes effect from the item's next period.

**Acceptance criteria:**
- [ ] A weekly item for Thursday created on Wednesday has this week's task; one for Tuesday has none until next week. A flexible "3 times a week" created on Saturday has two.
- [ ] Turned off and on in the same week, it gets its old tasks back, not new ones. Turned on in a later week, it gets that week's.
- [ ] Editing Tuesday to Thursday leaves this week's task where it is, and next week's is on Thursday's schedule.

**Verify:** `uv run pytest tests/test_recurring_items.py`.

**Dependencies:** 6.

**Files:** `app/recurring_items/rules.py`, `app/turnover/rules.py`, `tests/test_recurring_items.py`.

**Scope:** S

### Task 8: What closing will do, "Still matter?", and the upcoming list

**Description:** `Task` gains `atClose` and `stillMatters`, worked out in the task view queries. `getUpcoming`, `GET /api/tasks/upcoming`.

**Acceptance criteria:**
- [ ] `atClose` agrees with what closing then does, for every origin (one table test runs both).
- [ ] `stillMatters` is true after two rollovers of a hand-added or fixed-day task, never for a flexible task carrying inside its period, and not again until two more rollovers after an answer.
- [ ] The upcoming list holds open tasks with a later due date and no row, by due date, and none of another owner's.

**Verify:** `uv run pytest tests/test_week_read.py tests/test_upcoming.py tests/test_close_week.py`.

**Dependencies:** 5.

**Files:** `app/tasks/{models,routes,week}.py`, `db/queries/tasks.sql`, `app/db/`, `tests/test_week_read.py`, `tests/test_upcoming.py`.

**Scope:** M

### Task 9: Answer "Still matter?"

**Description:** `answerStillMatters`, `POST /api/tasks/{id}/still-matters`. Keep records the answer. Schedule records it and places the task by hand on the day. Drop records it and drops the task.

**Acceptance criteria:**
- [ ] After keep or schedule, `stillMatters` is false until two more rollovers. Schedule follows `placeTask`'s rules for the day and the week.
- [ ] Drop closes the task as dropped and keeps it in history. Sent twice, each answer changes nothing more.
- [ ] Another owner's task is a 404; a done or dropped task is a 409 (keep and schedule) or as `dropTask` (drop).

**Verify:** `uv run pytest tests/test_still_matters.py`.

**Dependencies:** 8.

**Files:** `app/tasks/{models,routes,rules}.py`, `db/queries/tasks.sql`, `app/db/`, `tests/test_still_matters.py`.

**Scope:** S

### Task 10: Docs, the contract and the front end's types

**Description:** `openapi.json` written; the spec marked built, with what changed while building; the map's shared decisions updated if a decision moved; `../docs/data-model.md` checked against what was built (it already has `closed_through_week`). In `../web-frontend`, on its own branch: `npm run api:types`, and the mock compiles against the new `Task` fields (the front end's plan, task 4).

**Acceptance criteria:**
- [ ] `tests/test_contract.py` passes with the new routes; every new operation is named as the front end will call it.
- [ ] The spec and the docs say what was built.
- [ ] The front end builds against the regenerated types.

**Verify:** the four checks; in `../web-frontend`, `npm run build`.

**Dependencies:** 6–9.

**Files:** `openapi.json`, `specs/week-turnover.md`, `specs/README.md`, `../docs/data-model.md`, `../web-frontend/src/api/openapi.ts`.

**Scope:** S

## Checkpoint: the slice
- [ ] The four checks pass; the spec's success criteria are met.
- [ ] The front end compiles against the new types.
