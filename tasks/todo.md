# Tasks: Goals and weekly targets (#5)

Plan: [`plan.md`](plan.md). Spec: [`../specs/goals-targets.md`](../specs/goals-targets.md).

Every task: write the tests first, run the four checks (`uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run pytest`), then one commit.

# PR: `goals-targets` (closes #5)

### Task 1: The goals table

**Description:** The migration: the shared columns, aspiration, type, label, measurable line, baseline, status, start date, deadline, ended on; the checks; `unique (id, user_id)` on aspirations and the two-column foreign key to it; `unique (id, user_id, type)` for weekly targets to point at; both triggers.

**Acceptance criteria:**
- [ ] The database refuses an unknown type or status, a blank label or line, a deadline before the start date, and `ended_on` that doesn't match the status.
- [ ] It refuses a goal under another owner's aspiration.
- [ ] `bin/dbmate up`, `rollback`, `up` leaves `db/schema.sql` unchanged.

**Verify:** `uv run pytest tests/test_goals_table.py`; `git diff --stat db/schema.sql` empty after the round trip.

**Dependencies:** none.

**Files:** `db/migrations/<ts>_goals.sql`, `db/schema.sql`, `tests/test_goals_table.py`.

### Task 2: The weekly_targets table

**Description:** The migration: the shared columns, goal, the fixed `goal_type`, kind, sessions, amount, unit, effective from; the checks; the foreign key to `goals (id, user_id, type)`; both triggers.

**Acceptance criteria:**
- [ ] The database refuses a target on a quitting or one-off goal, or on another owner's goal.
- [ ] It refuses a second row for one goal and week, an `effective_from` that isn't a Monday, sessions outside 1 to 14, and an amount that doesn't match the kind.
- [ ] Up, rollback, up leaves `db/schema.sql` unchanged.

**Verify:** `uv run pytest tests/test_weekly_targets_table.py`.

**Dependencies:** 1.

**Files:** `db/migrations/<ts>_weekly_targets.sql`, `db/schema.sql`, `tests/test_weekly_targets_table.py`.

### Task 3: Create, read and list goals

**Description:** The goals and weekly-target queries and their generated code; `app/weeks.py` (Monday of a day; the week a target change takes effect); `app/goals/` with `createGoal`, `getGoal` and `listGoals`; a building goal created with its first target.

**Acceptance criteria:**
- [ ] `PUT /api/goals/{id}` creates each of the three types; the same call again returns the goal as it is; a building goal without a target, or another type with one, is a 422; another user's aspiration is a 404; an id already another user's is a 409.
- [ ] `GET /api/goals/{id}` and `GET /api/goals` return the goal with its latest target and `slipped`, in the plan's order, never another user's.
- [ ] The first target takes effect this week, or next week when `planned_through_week` is later than the phone's week.

**Verify:** `uv run pytest tests/test_goals.py tests/test_weeks.py`.

**Dependencies:** 1, 2.

**Files:** `db/queries/goals.sql`, `db/queries/weekly_targets.sql`, `app/db/*` (generated), `app/weeks.py`, `app/goals/{routes,models,rules}.py`, `app/main.py`, `tests/test_goals.py`, `tests/test_weeks.py`.

### Task 4: Edit a goal

**Description:** `updateGoal`: label, line, baseline, aspiration and deadline, sent whole.

**Acceptance criteria:**
- [ ] The fields change; a deadline pushed back clears `slipped`; one before the start date is a 422 (the database refuses it too).
- [ ] Moving to an active aspiration works; to a retired one is a 409; to another user's is a 404; keeping a retired aspiration is fine.
- [ ] Another user's goal is a 404.

**Verify:** `uv run pytest tests/test_goals.py`.

**Dependencies:** 3.

**Files:** `db/queries/goals.sql`, `app/db/goals.py`, `app/goals/*`, `tests/test_goals.py`.

### Task 5: Set the weekly target

**Description:** `setWeeklyTarget`, count or amount, in the week the plan's rule gives.

**Acceptance criteria:**
- [ ] A change this week replaces this week's row; once next week is open it adds a row for next week, and this week's row is as it was.
- [ ] Last week's row is still there after a change.
- [ ] A quitting or one-off goal is a 409; a body that doesn't match its kind is a 422.

**Verify:** `uv run pytest tests/test_goals.py`.

**Dependencies:** 3.

**Files:** `db/queries/weekly_targets.sql`, `app/db/weekly_targets.py`, `app/goals/*`, `tests/test_goals.py`.

## Checkpoint A

- [ ] The four checks pass.
- [ ] `openapi.json` regenerated; the contract tests list the new operations.

### Task 6: The six status changes

**Description:** Pause, resume, end, mark reached, reopen and go again, driven by the plan's table.

**Acceptance criteria:**
- [ ] Each allowed change works and sets or clears `endedOn`; each refused one is a 409; each repeat returns the goal unchanged and writes no audit row.
- [ ] Resume, reopen and go again work under a retired aspiration.
- [ ] Go again keeps the goal's target as it was.

**Verify:** `uv run pytest tests/test_goal_status.py`.

**Dependencies:** 3.

**Files:** `db/queries/goals.sql`, `app/db/goals.py`, `app/goals/*`, `tests/test_goal_status.py`.

### Task 7: Retiring an aspiration pauses its goals

**Description:** `retireAspiration` takes `itsWork`. With `pause`, its active goals are paused in the same transaction.

**Acceptance criteria:**
- [ ] `pause` pauses its active goals and leaves its other goals and other aspirations' goals as they were; `keep` changes no goal.
- [ ] Retiring again changes nothing; bringing it back resumes no goal.
- [ ] A body without `itsWork` is a 422.

**Verify:** `uv run pytest tests/test_aspirations.py`.

**Dependencies:** 6.

**Files:** `app/aspirations/{routes,models,rules}.py`, `db/queries/goals.sql`, `app/db/goals.py`, `tests/test_aspirations.py`.

### Task 8: Docs and the contract

**Description:** `openapi.json`; the spec marked built with its open questions settled; the front-end criterion moved to #40 with a note there listing where its types differ; `CLAUDE.md`'s layout; `data-model.md` or `flows.md` only if a line no longer holds.

**Acceptance criteria:**
- [ ] `openapi.json` is up to date, and the contract tests name the new operations.
- [ ] The spec and docs say what was built.

**Verify:** the four checks.

**Dependencies:** 1 to 7.

**Files:** `openapi.json`, `specs/goals-targets.md`, `specs/README.md`, `CLAUDE.md`, `tests/test_contract.py`.

## Checkpoint B

- [ ] Every spec success criterion met, or moved to #40 by agreement.
- [ ] The four checks pass; PR opened.
