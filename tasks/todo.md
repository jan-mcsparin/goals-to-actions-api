# Tasks: Delete (#12)

Plan: [`plan.md`](plan.md). Spec: [`../specs/delete.md`](../specs/delete.md).

Every task: write the tests first, run the four checks (`uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run pytest`), then one commit.

# PR: `delete` (closes #12)

### Task 1: Positions ignore deleted rows

**Description:** One migration swaps `aspirations_position_unique` and `milestones_position_unique` for deferrable exclusion constraints of the same names over rows not deleted. Down puts the unique constraints back.

**Acceptance criteria:**
- [ ] Two live rows still can't share a position; a deleted row and a live one can (a test each, per table).
- [ ] Reordering still works (the existing tests pass).
- [ ] Up, rollback, up leaves `db/schema.sql` unchanged.

**Verify:** `uv run pytest tests/test_aspirations_table.py tests/test_milestones_table.py`, then the four checks.

**Dependencies:** none.

**Files:** `db/migrations/<ts>_positions_ignore_deleted.sql`, `db/schema.sql`, `tests/test_aspirations_table.py`, `tests/test_milestones_table.py`.

**Scope:** S

### Task 2: Delete a task

**Description:** `deleteTask`, `DELETE /api/tasks/{taskId}`, 204. `rules.delete` takes the user lock, hides the task and its week records. Turnover's `DeleteTask` and `DeleteTaskRows` move to `tasks.sql` and `task_weeks.sql`; `TaskDeleted` finds a repeat.

**Acceptance criteria:**
- [ ] The task and its rows leave the week read, the upcoming list and its goal's progress.
- [ ] Deleting twice gives 204 and changes nothing; another user's task gives 404; the audit log names "delete task".
- [ ] A deleted goal session isn't made again when its week is opened twice.

**Verify:** `uv run pytest tests/test_delete_task.py`, then the four checks.

**Dependencies:** 1.

**Files:** `db/queries/{tasks,task_weeks,turnover}.sql`, `app/db/`, `app/tasks/{routes,rules}.py`, `app/turnover/`, `tests/test_delete_task.py`, `tests/test_user_lock.py`.

**Scope:** M

### Task 3: Delete a recurring item

**Description:** `deleteRecurringItem`, `DELETE /api/recurring-items/{itemId}`, 204. Hides the item and its open tasks with their rows; its other tasks lose the link and keep their origin.

**Acceptance criteria:**
- [ ] Its open tasks leave the week; a done one stays in the week, with no item.
- [ ] The item isn't listed and makes no tasks when the next week opens.
- [ ] Twice, another user's, and the audit action, as task 2.

**Verify:** `uv run pytest tests/test_delete_item.py`, then the four checks.

**Dependencies:** 2.

**Files:** `db/queries/{recurring_items,tasks}.sql`, `app/db/`, `app/recurring_items/{routes,rules}.py`, `tests/test_delete_item.py`, `tests/test_user_lock.py`.

**Scope:** M

## Checkpoint: after task 3

- [ ] The four checks pass.

### Task 4: Delete a milestone

**Description:** `deleteMilestone`, `DELETE /api/milestones/{milestoneId}`, returns the goal's page. Hides the milestone and its check-ins and closes the gap in the goal's positions.

**Acceptance criteria:**
- [ ] Deleting the second of three leaves 1 and 2; a milestone added afterwards is 3.
- [ ] Its check-ins leave the page's results; Next moves on if it was Next.
- [ ] Twice returns the page again; another user's gives 404; the audit action.

**Verify:** `uv run pytest tests/test_delete_milestone.py`, then the four checks.

**Dependencies:** 1.

**Files:** `db/queries/{milestones,check_ins}.sql`, `app/db/`, `app/milestones/{routes,rules}.py`, `tests/test_delete_milestone.py`, `tests/test_user_lock.py`.

**Scope:** S

### Task 5: Delete a goal

**Description:** `deleteGoal`, `DELETE /api/goals/{goalId}`, 204. Hides the goal, its tasks and their rows, milestones, check-ins, weekly targets, quit days and urge ratings; empties `from_goal_id` on an item continued from it.

**Acceptance criteria:**
- [ ] A building goal with sessions, milestones and check-ins; a quitting goal with days and urges; a one-off with steps: each leaves every read, along with what it had.
- [ ] An item continued from it stays, with no `fromGoalId`.
- [ ] Twice, another user's, and the audit action.

**Verify:** `uv run pytest tests/test_delete_goal.py`, then the four checks.

**Dependencies:** 2, 4.

**Files:** `db/queries/{goals,tasks,task_weeks,milestones,check_ins,weekly_targets,quit_days,urge_ratings,recurring_items}.sql`, `app/db/`, `app/goals/{routes,rules}.py`, `tests/test_delete_goal.py`, `tests/test_user_lock.py`.

**Scope:** M

### Task 6: Delete an aspiration

**Description:** `deleteAspiration`, `DELETE /api/aspirations/{aspirationId}`, 204. Its goals and items lose the link; an active aspiration's gap is closed.

**Acceptance criteria:**
- [ ] Deleting the first of three leaves 1 and 2; one created afterwards is 3. A retired one is deleted with no renumbering.
- [ ] Its goals list with no aspiration; its items with none.
- [ ] Twice, another user's, and the audit action.

**Verify:** `uv run pytest tests/test_delete_aspiration.py`, then the four checks.

**Dependencies:** 1.

**Files:** `db/queries/{aspirations,goals,recurring_items}.sql`, `app/db/`, `app/aspirations/{routes,rules}.py`, `tests/test_delete_aspiration.py`, `tests/test_user_lock.py`.

**Scope:** S

## Checkpoint: after task 6

- [ ] The four checks pass; all five deletes work.

### Task 7: No read shows a deleted row; docs, the contract and the front end's types

**Description:** A sweep test makes one of everything, deletes it, and checks every read. `openapi.json` written; the spec marked built with what changed; the map, `CLAUDE.md` and `../docs/` (data model, flows) updated. In `../web-frontend`, on its own branch: `npm run api:types`, and the mock compiles.

**Acceptance criteria:**
- [ ] No read returns a deleted row or a link to one.
- [ ] `tests/test_contract.py` lists the five operations.
- [ ] The front end builds against the regenerated types, and its tests pass.

**Verify:** the four checks; in `../web-frontend`, `nvm use`, then its lint, tests and build.

**Dependencies:** 1–6.

**Files:** `tests/test_deleted_rows.py`, `tests/test_contract.py`, `openapi.json`, `specs/delete.md`, `specs/README.md`, `CLAUDE.md`, `../docs/data-model.md`, `../docs/flows.md`, `../web-frontend/src/api/openapi.ts`.

**Scope:** M

## Checkpoint: complete

- [ ] The four checks pass.
- [ ] The front end compiles against the new types.
- [ ] Every success criterion in the spec is met.
