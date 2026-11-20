# Tasks: The planner (#10)

Plan: [`plan.md`](plan.md). Spec: [`../specs/planner.md`](../specs/planner.md).

Every task: write the tests first, run the four checks (`uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run pytest`), then one commit.

# PR: `planner` (closes #10)

### Task 1: The placing rule

**Description:** In `app/planner.py`, pure code: `place(week, first_day, load, new_work)` returns where each new task goes. Fixed-day tasks on their day (or the first day allowed, if their day is earlier); a group's tasks spread evenly, _d_/_n_ days apart rounded down, starting where the chosen days are lightest, ties to the earlier start; new work for a group that already has tasks this week on the lightest day without one of its tasks. Groups take their turn in the given order, each seeing the load the earlier ones left. Nothing placed if no day is left. Nothing calls it yet.

**Acceptance criteria:**
- [x] A table test with one case per rule, plus: the empty week, a week first opened on Wednesday, more sessions than days, two goals competing for the lighter days, a day already over the cap, and a goal starting Friday.
- [x] Property tests: every placement is inside the week and on or after the first day; only the given tasks are placed; the same input gives the same output.

**Verify:** `uv run pytest tests/test_planner_rule.py`, then the four checks.

**Dependencies:** none.

**Files:** `app/planner.py`, `tests/test_planner_rule.py`.

**Scope:** S

### Task 2: Place when a week opens

**Description:** `place_new_work` reads, for the tasks it's given, each one's group, order, fixed day and start date, and the week's load (`db/queries/planner.sql`, `ListPlacementContext` and `ListDayLoads`), calls `place`, and writes each placement with `PlaceGeneratedTask`, which only touches a bank row not placed by hand, with no outcome, on a day on or after the first day. `sqlc generate`.

**Acceptance criteria:**
- [x] Opened on Sunday evening, next week's fixed-day tasks are on their days and its sessions and flexible tasks are spread from Monday.
- [x] Opened by a first request on Wednesday, the current week's recurring work is placed from Wednesday on.
- [x] Carry-overs, tasks now due and tasks added by hand are in the bank after the week opens.
- [x] `PlaceGeneratedTask` changes nothing for a hand-placed row, a row already on a day, or a day before the first day (a test for each).

**Verify:** `uv run pytest tests/test_planner.py tests/test_open_week.py`, then the four checks.

**Dependencies:** 1.

**Files:** `app/planner.py`, `db/queries/planner.sql`, `app/db/`, `tests/test_planner.py`, and any `tests/test_open_week.py` cases that expect recurring work in the bank.

**Scope:** M

### Task 3: Place new recurring work on later days

**Description:** No new code paths: `fill_goal` and `fill_item` already hand their new tasks over with tomorrow as the first day. This task proves it through the API and fixes whatever the tests find.

**Acceptance criteria:**
- [ ] A building goal made on Tuesday has its sessions on Wednesday or later; one made on Sunday leaves them in the bank.
- [ ] A raised target's extra session goes on the lightest later day without one of the goal's sessions.
- [ ] A new flexible item, an item turned back on and a resumed goal place only their fresh tasks; the tasks they got back stay where they were.
- [ ] Today's tasks, read before and after each of those, are byte-for-byte the same; a check-off made early and a task sent to the bank leave every other row as it was.

**Verify:** `uv run pytest tests/test_planner.py`, then the four checks.

**Dependencies:** 2.

**Files:** `tests/test_planner.py`, and fixes in `app/planner.py` or `app/turnover/rules.py` if needed.

**Scope:** S

## Checkpoint: after task 3

- [ ] The four checks pass.
- [ ] Recurring work lands on days when a week opens and as it arrives; nothing else moves.

### Task 4: A new fixed-day item due today goes on today

**Description:** Creating a weekly or monthly item, or turning one back on, whose day is today puts today's task on today in the same transaction, because the person just asked for it (spec, "Left to other slices"). Not a planner write: the recurring-items rule does it.

**Acceptance criteria:**
- [ ] Created on Wednesday for "every Wednesday", the task is on today; for "every Thursday", the planner puts it on Thursday.
- [ ] Sent twice, it changes nothing more.

**Verify:** `uv run pytest tests/test_recurring_items.py tests/test_item_tasks.py`, then the four checks.

**Dependencies:** 2.

**Files:** `app/recurring_items/rules.py` or `app/turnover/rules.py` (`fill_item`), `tests/test_item_tasks.py`.

**Scope:** S

### Task 5: The full-day mark

**Description:** `Week` gains `days`: seven `DayMark { day, cap, full }`. `cap` from the user's intensity (3, 4 or 6); `full` when the day holds at least `cap` tasks that are open or done. Worked out in `app/tasks/week.py` from the rows it already reads.

**Acceptance criteria:**
- [ ] A day with four tasks on Normal is full; with three it isn't; a dropped task doesn't count.
- [ ] Changing intensity (set directly in the test until `settings-sync`) changes only `cap` and `full`; every task stays where it was.

**Verify:** `uv run pytest tests/test_week_read.py`, then the four checks.

**Dependencies:** none (after 2 so the tests read placed weeks).

**Files:** `app/tasks/models.py`, `app/tasks/week.py`, `tests/test_week_read.py`.

**Scope:** S

### Task 6: Docs, the contract and the front end's types

**Description:** `openapi.json` written; the spec marked built, with what changed while building; the map's slice row and `CLAUDE.md`'s line for `planner.py` updated; `../docs/data-model.md` and `../docs/flows.md` checked against what was built. In `../web-frontend`, on its own branch: `npm run api:types`, and the mock compiles against `Week.days`.

**Acceptance criteria:**
- [ ] `tests/test_contract.py` passes; `DayMark` is camelCase.
- [ ] The front end builds against the regenerated types.

**Verify:** the four checks; in `../web-frontend`, `nvm use`, then its build and tests.

**Dependencies:** 1–5.

**Files:** `openapi.json`, `specs/planner.md`, `specs/README.md`, `CLAUDE.md`, `../docs/`, `../web-frontend/src/api/` (generated types and the mock).

**Scope:** M

## Checkpoint: complete

- [ ] The four checks pass.
- [ ] The front end compiles against the new types.
- [ ] Every success criterion in the spec is met.
