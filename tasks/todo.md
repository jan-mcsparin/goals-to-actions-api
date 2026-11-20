# Tasks: Quitting goals (#11)

Plan: [`plan.md`](plan.md). Spec: [`../specs/quitting-goals.md`](../specs/quitting-goals.md).

Every task: write the tests first, run the four checks (`uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run pytest`), then one commit.

# PR: `quitting-goals` (closes #11)

### Task 1: The quit_days and urge_ratings tables

**Description:** One migration adds both tables with the shared columns and triggers, `goal_type` fixed to `'quitting'` with a foreign key to `goals (id, user_id, type)`, `urge_ratings.level` checked, and a unique index on `(goal_id, day)` / `(goal_id, rated_on)` over rows not deleted. Queries in `db/queries/quit_days.sql` and `db/queries/urge_ratings.sql`: upsert, clear, the day's row, and the rows in a range. `sqlc generate`.

**Acceptance criteria:**
- [x] The database refuses a row on a building or one-off goal, on another owner's goal, a second live row for a day, and an unknown urge level (a test each).
- [x] Up, rollback, up leaves `db/schema.sql` unchanged.

**Verify:** `uv run pytest tests/test_quit_days_table.py`, then the four checks.

**Dependencies:** none.

**Files:** `db/migrations/<ts>_quit_days_and_urges.sql`, `db/schema.sql`, `db/queries/quit_days.sql`, `db/queries/urge_ratings.sql`, `app/db/`, `tests/test_quit_days_table.py`.

**Scope:** M

### Task 2: Answer and clear a day

**Description:** `app/quitting/` with `answerQuitDay` and `clearQuitDay`. `rules.py` checks the goal is yours (404), quitting, and the day is from its start to today (409), then upserts or clears. Both return the day's `QuitDay`.

**Acceptance criteria:**
- [x] A day is answered, changed and cleared; each repeat changes nothing more, and the day has at most one live row throughout.
- [x] A building goal, a day before the start and tomorrow are refused with 409; another user's goal with 404; no `X-Time-Zone` with 422.
- [x] A day a week old can still be answered; the audit log names the action.

**Verify:** `uv run pytest tests/test_quit_days.py`, then the four checks.

**Dependencies:** 1.

**Files:** `app/quitting/{__init__,routes,models,rules}.py`, `app/main.py`, `tests/test_quit_days.py`.

**Scope:** M

### Task 3: Rate and clear the urge

**Description:** `rateUrge` and `clearUrgeRating`, the same way, in the same slice. Each returns the whole `QuitDay`, so after rating the urge the phone still has the day's answer.

**Acceptance criteria:**
- [x] An urge is rated, changed and cleared, with the same refusals as task 2.
- [x] Rating the urge leaves the day's answer as it was, and the other way round.

**Verify:** `uv run pytest tests/test_urges.py`, then the four checks.

**Dependencies:** 2.

**Files:** `app/quitting/{routes,models,rules}.py`, `tests/test_urges.py`.

**Scope:** S

## Checkpoint: after task 3

- [x] The four checks pass.
- [x] The four writes work and are safe to repeat.

### Task 4: The record on the goal's page

**Description:** `app/quitting/record.py`: `quit_record(connection, user_id, goal, today)` reads both tables for the last 28 days, and the goal's answers since its start to work out `heldRun` and `unknownInRun`. `GoalPage` gains `quitRecord`, filled for quitting goals.

**Acceptance criteria:**
- [x] Unanswered days read `held: null`; a gap neither ends nor adds to the run; a "no" starts it again.
- [x] `unknownInRun` counts unanswered days since the last "no" (or the start), not today; answering one lowers it, and a gap before the last "no" isn't counted.
- [x] A goal started 3 days ago shows 4 days; one started long ago shows 28. Building and one-off goals have no record.

**Verify:** `uv run pytest tests/test_quit_record.py tests/test_milestones.py`, then the four checks.

**Dependencies:** 2, 3.

**Files:** `app/quitting/record.py`, `app/milestones/models.py`, `app/milestones/page.py`, `tests/test_quit_record.py`.

**Scope:** M

### Task 5: Quitting goals on the week read

**Description:** `Week` gains `quittingGoals`: each active quitting goal started by the week's end, with a `QuitDay` for each day of the week from its start.

**Acceptance criteria:**
- [x] An answered and a rated day show in the week; a paused quitting goal and a building goal don't appear.
- [x] A goal started on Wednesday has days Wednesday to Sunday.

**Verify:** `uv run pytest tests/test_week_read.py`, then the four checks.

**Dependencies:** 4 (shares `record.py`).

**Files:** `app/tasks/models.py`, `app/tasks/week.py`, `app/quitting/record.py`, `tests/test_week_read.py`.

**Scope:** S

### Task 6: Docs, the contract and the front end's types

**Description:** `openapi.json` written; the spec marked built, with what changed while building; the map and `CLAUDE.md` (the new slice folder) updated; `../docs/data-model.md` checked against what was built (the server-made id, clearing). In `../web-frontend`, on its own branch: `npm run api:types`, and the mock compiles.

**Acceptance criteria:**
- [x] `tests/test_contract.py` passes; every operation is named as the front end will call it.
- [x] The front end builds against the regenerated types, and its tests pass.

**Verify:** the four checks; in `../web-frontend`, `nvm use`, then its lint, tests and build.

**Dependencies:** 1–5.

**Files:** `openapi.json`, `specs/quitting-goals.md`, `specs/README.md`, `CLAUDE.md`, `../docs/data-model.md`, `../web-frontend/src/api/openapi.ts`.

**Scope:** M

## Checkpoint: complete

- [x] The four checks pass.
- [x] The front end compiles against the new types.
- [x] Every success criterion in the spec is met.
