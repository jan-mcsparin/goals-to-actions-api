# Tasks: Recurring items (#8)

Plan: [`plan.md`](plan.md). Spec: [`../specs/recurring-items.md`](../specs/recurring-items.md).

Every task: write the tests first, run the four checks (`uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run pytest`), then one commit.

# PR: `recurring-items` (closes #8)

### Task 1: The recurring_items table, and the tasks foreign key

**Description:** The migration: the shared columns; name, aspiration, from goal, schedule kind, weekday, day of month, times, period, starts on, active; both triggers; the check that the schedule columns fit the kind. The foreign key from `tasks (recurring_item_id, user_id)`. Queries in `db/queries/recurring_items.sql`.

**Acceptance criteria:**
- [x] The database refuses every mismatched schedule: a weekly item without a weekday or with a day of month, times or period; the same for monthly and flexible; a weekday outside 1–7, a day of month outside 1–28, times outside 1–6, times above 1 for two weeks or a month.
- [x] It refuses another owner's aspiration, goal, or (from `tasks`) item, and a blank name.
- [x] Up, rollback, up leaves `db/schema.sql` unchanged.

**Verify:** `uv run pytest tests/test_recurring_items_table.py`.

**Dependencies:** none.

**Files:** `db/migrations/<ts>_recurring_items.sql`, `db/queries/recurring_items.sql`, `db/schema.sql`, `app/db/`, `tests/test_recurring_items_table.py`.

### Task 2: Create and list

**Description:** `app/recurring_items/` with `models.py` (the item, the schedule as a union on `kind`, `NewRecurringItem`), `rules.py` and `routes.py`; the router in `main.py`. `createRecurringItem` and `listRecurringItems`.

**Acceptance criteria:**
- [x] Each of the three kinds can be created and comes back in the list, off ones included, deleted ones left out.
- [x] Sent twice, create makes one item; a retired aspiration is a 409; another owner's aspiration or goal is a 404; a bad schedule is a 422.
- [x] A reached goal's practice is kept with `fromGoalId` set. The audit log has the action.

**Verify:** `uv run pytest tests/test_recurring_items.py`; the schedule in `openapi.json` is a `oneOf` on `kind`.

**Dependencies:** 1.

**Files:** `app/recurring_items/{__init__,models,rules,routes}.py`, `app/main.py`, `tests/test_recurring_items.py`, `tests/test_user_lock.py` if it locks.

### Task 3: Edit

**Description:** `updateRecurringItem`, sent whole: name, aspiration, schedule, starts on.

**Acceptance criteria:**
- [x] Changing kind clears the old kind's fields; moving to no aspiration makes it maintenance.
- [x] A retired aspiration is a 409; an unknown or another owner's item is a 404; sent twice, the second changes nothing.

**Verify:** `uv run pytest tests/test_recurring_items.py`.

**Dependencies:** 2.

**Files:** `app/recurring_items/{models,rules,routes}.py`, `db/queries/recurring_items.sql`, `app/db/`, `tests/test_recurring_items.py`.

## Checkpoint: items can be made and edited
- [x] The four checks pass.

### Task 4: Turn off and on

**Description:** `turnOffRecurringItem` and `turnOnRecurringItem`. The set-aside and bring-back code in `app/tasks/rules.py` takes the rows to act on, so goals and items share it. A task_weeks query lists an item's rows.

**Acceptance criteria:**
- [x] Off sets the item's open tasks aside in every open week, in the bank, on days and placed by hand; done ones stay. On returns those whose week is still open to that week's bank; one from a closed week doesn't come back.
- [x] Turning on an item whose aspiration is retired clears the aspiration. Both are safe to repeat and take the user lock.
- [x] The goal status tests pass unchanged.

**Verify:** `uv run pytest tests/test_recurring_items.py tests/test_goal_status.py tests/test_user_lock.py`.

**Dependencies:** 2.

**Files:** `app/recurring_items/{rules,routes}.py`, `app/tasks/rules.py`, `app/goals/rules.py`, `db/queries/task_weeks.sql`, `app/db/`, tests.

### Task 5: Retiring an aspiration reaches its items and its goals' tasks

**Description:** `aspirations.rules.retire`: "pause" turns its active items off and sets aside the tasks of the goals and items it paused; "keep" clears its items' aspiration.

**Acceptance criteria:**
- [x] With "pause", the aspiration's goals' and items' open tasks leave the days and the bank in every open week; done ones stay.
- [x] With "keep", its items have no aspiration and its goals keep theirs. Bringing it back leaves items off and unlinked.
- [x] Retiring twice changes nothing.

**Verify:** `uv run pytest tests/test_aspirations.py`.

**Dependencies:** 4.

**Files:** `app/aspirations/rules.py`, `db/queries/goals.sql`, `db/queries/recurring_items.sql`, `app/db/`, `tests/test_recurring_items.py`, `tests/test_goal_tasks.py`.

### Task 6: Docs, the contract and the front end's types

**Description:** `openapi.json`; the spec finalised (status, contract, settled questions); `specs/README.md` notes; `../docs/data-model.md` (starts on, worked out by the front end and turnover), `../docs/flows.md` if retire's wording changes. In `web-frontend`, on its own branch: regenerate the types and make the mock client compile against them.

**Acceptance criteria:**
- [x] `openapi.json` is regenerated and the contract test passes.
- [x] The docs say what was built and decided.
- [ ] The front end's types are regenerated and its checks pass (`nvm use` first).

**Verify:** the four checks here; `npm run lint`, `npm run typecheck` (or the repo's equivalent) and `npm test` in `web-frontend`.

**Dependencies:** 5.

**Files:** `openapi.json`, `specs/recurring-items.md`, `specs/README.md`, `../docs/data-model.md`, `../web-frontend/src/api/openapi.ts`.

## Checkpoint: the slice
- [ ] Every success criterion in the spec is met.
- [ ] The four checks pass; the PR is open.
