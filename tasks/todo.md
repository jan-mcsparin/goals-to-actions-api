# Tasks: Milestones and check-ins (#6)

Plan: [`plan.md`](plan.md). Spec: [`../specs/milestones-check-ins.md`](../specs/milestones-check-ins.md).

Every task: write the tests first, run the four checks (`uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run pytest`), then one commit.

# PR: `milestones-check-ins` (closes #6)

### Task 1: The milestones table

**Description:** The migration: the shared columns, goal, the fixed `goal_type`, position, measurable line, target date, status; the checks; the foreign key to `goals (id, user_id, type)`; position unique per goal, checked when each statement ends; `unique (id, goal_id)`; both triggers.

**Acceptance criteria:**
- [x] The database refuses a milestone on a one-off goal or on another owner's goal, two in one position on a goal, a position below 1, a blank line and an unknown status.
- [x] One statement can swap two positions.
- [x] Up, rollback, up leaves `db/schema.sql` unchanged.

**Verify:** `uv run pytest tests/test_milestones_table.py`.

**Dependencies:** none.

**Files:** `db/migrations/<ts>_milestones.sql`, `db/schema.sql`, `tests/test_milestones_table.py`.

### Task 2: The check_ins table

**Description:** The migration: the shared columns, goal, milestone (optional), outcome, result, checked in on; the foreign keys to `goals (id, user_id)` and `milestones (id, goal_id)`; both triggers.

**Acceptance criteria:**
- [x] The database refuses a check-in naming another goal's milestone, another owner's goal, or an unknown outcome.
- [x] Several check-ins for one milestone are kept.
- [x] Up, rollback, up leaves `db/schema.sql` unchanged.

**Verify:** `uv run pytest tests/test_check_ins_table.py`.

**Dependencies:** 1.

**Files:** `db/migrations/<ts>_check_ins.sql`, `db/schema.sql`, `tests/test_check_ins_table.py`.

### Task 3: Add a milestone, and the goal's page

**Description:** The queries; `app/milestones/`; `addMilestone`; `getGoal` returning the goal's page.

**Acceptance criteria:**
- [x] `PUT /api/milestones/{id}` adds a milestone last; the same call again returns the page as it is; a one-off goal is a 409; a date outside the goal's start and deadline is a 409; another user's goal is a 404.
- [x] `getGoal` returns the goal, its milestones in order, `progress` ("0 of 1" with none), and `latest`.

**Verify:** `uv run pytest tests/test_milestones.py`.

**Dependencies:** 1, 2.

**Files:** `db/queries/milestones.sql`, `db/queries/check_ins.sql`, `app/db/*` (generated), `app/milestones/{routes,models,rules}.py`, `app/goals/routes.py`, `app/main.py`, `tests/test_milestones.py`, `tests/test_goals.py`.

### Task 4: Edit a milestone, with dates pushed out

**Description:** `updateMilestone` (line and date, sent whole); a "not yet" goes back to upcoming; a later date pushes later dated milestones out; `updateGoal` refuses a deadline before a milestone's date.

**Acceptance criteria:**
- [x] A date moved later by n days moves every later dated milestone by n, none past the deadline; undated ones stay undated; moving earlier moves nothing else.
- [x] Editing a "not yet" makes it upcoming and adds no check-in; editing a hit one keeps it hit.
- [x] `updateGoal` with a deadline before a milestone's date is a 409.

**Verify:** `uv run pytest tests/test_milestones.py tests/test_goals.py`.

**Dependencies:** 3.

**Files:** `db/queries/milestones.sql`, `app/milestones/*`, `app/goals/rules.py`, `tests/test_milestones.py`, `tests/test_goals.py`.

## Checkpoint A

- [x] The four checks pass; `openapi.json` regenerated.

### Task 5: Reorder milestones

**Description:** `reorderMilestones`, every milestone of the goal once.

**Acceptance criteria:**
- [x] The order changes; positions stay 1 to n.
- [x] A list that isn't exactly the goal's milestones is a 409; another user's goal is a 404.

**Verify:** `uv run pytest tests/test_milestones.py`.

**Dependencies:** 3.

**Files:** `app/milestones/*`, `db/queries/milestones.sql`, `tests/test_milestones.py`.

### Task 6: Check in

**Description:** `checkIn` against Next: a check-in row, the milestone's status, and the goal reached on a hit of its own line.

**Acceptance criteria:**
- [x] A hit or not yet on Next adds a check-in dated the phone's today and sets the milestone's status; a not-yet milestone stays Next.
- [x] A hit on the goal's own line, once every milestone is hit, marks the goal reached with today's `endedOn`; a not yet there changes only the history.
- [x] Anything but Next is a 409, as is a reached or ended goal; the same check-in twice adds one row; `latest` skips check-ins with no result; `progress` counts the goal once reached.

**Verify:** `uv run pytest tests/test_check_ins.py`.

**Dependencies:** 3.

**Files:** `db/queries/check_ins.sql`, `db/queries/milestones.sql`, `app/milestones/*`, `tests/test_check_ins.py`.

### Task 7: Keep a "not yet"

**Description:** `keepMilestone`: back to upcoming with its line and date as they are.

**Acceptance criteria:**
- [x] A "not yet" becomes upcoming and the check-in history is untouched.
- [x] Sent again, or on an upcoming milestone, it changes nothing; on a hit one it's a 409.

**Verify:** `uv run pytest tests/test_check_ins.py`.

**Dependencies:** 6.

**Files:** `app/milestones/*`, `db/queries/milestones.sql`, `tests/test_check_ins.py`.

### Task 8: Docs and the contract

**Description:** `openapi.json`; the spec marked built with its open questions settled; `CLAUDE.md`'s layout; `data-model.md` and `flows.md` only if a line no longer holds; a follow-up comment on front-end #40.

**Acceptance criteria:**
- [x] `openapi.json` is up to date, and the contract tests name the new operations.
- [x] The spec and docs say what was built.

**Verify:** the four checks.

**Dependencies:** 1 to 7.

**Files:** `openapi.json`, `specs/milestones-check-ins.md`, `CLAUDE.md`, `tests/test_contract.py`.

## Checkpoint B

- [x] Every spec success criterion met, the front end's moved to #40 as before.
- [x] The four checks pass; PR opened.
