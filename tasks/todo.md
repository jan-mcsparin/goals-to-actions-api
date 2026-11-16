# Tasks: Aspirations (#4)

Plan: [`plan.md`](plan.md). Spec: [`../specs/aspirations.md`](../specs/aspirations.md).

Every task: write the tests first, run the four checks (`uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run pytest`), then one commit.

# PR: `aspirations` (closes #4)

### Task 1: The aspirations table

**Description:** The migration: the shared columns, `name`, `why`, `status`, `position`, `retired_on`, the check that ties status to position and retired day, the unique position per owner checked at the end of each statement, and both triggers.

**Acceptance criteria:**
- [x] The database refuses two active aspirations of one owner in the same position, and allows a one-statement renumber that swaps two.
- [x] It refuses an active row with no position, a retired row with a position or no retired day, a blank name and an unknown status.
- [x] `bin/dbmate up`, `rollback`, `up` leaves `db/schema.sql` unchanged.

**Verify:** `uv run pytest tests/test_aspirations_table.py`; `git diff --stat db/schema.sql` empty after the round trip.

**Dependencies:** none.

**Files:** `db/migrations/<ts>_aspirations.sql`, `db/schema.sql`, `tests/test_aspirations_table.py`.

### Task 2: List and create

**Description:** The first routes and the pieces every later route uses: the queries and generated code, the router and models, the `client` fixture, and the owner lock.

**Acceptance criteria:**
- [x] `PUT /aspirations/{id}` creates an aspiration last among the active; the same call again returns the row as it is and makes no second row or audit row.
- [x] `GET /aspirations` returns the active ones by position, then the retired ones; never another user's.
- [x] A blank name is 422; an id that is another user's row is 409; the create's audit row carries the user and "create aspiration".

**Verify:** `uv run pytest tests/test_aspirations.py tests/test_contract.py`.

**Dependencies:** 1.

**Files:** `db/queries/aspirations.sql`, `app/db/` (generated), `app/aspirations/` (`routes.py`, `models.py`, `rules.py`), `app/errors.py`, `app/main.py`, `tests/conftest.py`, `tests/test_aspirations.py`.

### Task 3: Reorder

**Description:** `POST /aspirations/reorder` renumbers the active aspirations from the ids sent, in one statement if sqlc allows.

**Acceptance criteria:**
- [ ] The active aspirations come back in the order sent, numbered 1 to n; retired ones are untouched.
- [ ] A list that leaves out, repeats or adds an id (retired, unknown or another user's) is 409 and changes nothing.
- [ ] Sending the same order twice is fine; the audit rows carry "reorder aspirations".

**Verify:** `uv run pytest tests/test_aspirations.py`.

**Dependencies:** 2.

**Files:** `db/queries/aspirations.sql`, `app/db/` (generated), `app/aspirations/` (`routes.py`, `models.py`, `rules.py`), `tests/test_aspirations.py`.

**Checkpoint:** report whether the one-statement reorder generated cleanly or the fallback was used.

### Task 4: Edit

**Description:** `PATCH /aspirations/{id}` sets name and why.

**Acceptance criteria:**
- [ ] Name and why change; `why: null` empties it; position and status don't move; it works on a retired aspiration.
- [ ] An unknown id or another user's is 404, in FastAPI's `{"detail": ...}` shape; a blank name is 422.
- [ ] The audit row carries "update aspiration".

**Verify:** `uv run pytest tests/test_aspirations.py`.

**Dependencies:** 2.

**Files:** `db/queries/aspirations.sql`, `app/db/` (generated), `app/aspirations/routes.py`, `app/aspirations/models.py`, `tests/test_aspirations.py`.

### Task 5: Retire and bring back

**Description:** The two actions, and the `today` dependency that reads the `X-Time-Zone` header.

**Acceptance criteria:**
- [ ] Retiring empties the position, sets the retired day to today in the header's time zone, and closes the gap so the rest are 1 to n. Retiring twice changes nothing and writes no audit row.
- [ ] Bringing back makes it active and last, with no retired day. Bringing back an active one changes nothing.
- [ ] A missing or unknown time zone on retire is 422; an unknown id or another user's is 404; the audit rows carry "retire aspiration" and "bring back aspiration".

**Verify:** `uv run pytest tests/test_aspirations.py tests/test_time_zone.py`.

**Dependencies:** 2.

**Files:** `db/queries/aspirations.sql`, `app/db/` (generated), `app/time_zone.py`, `app/aspirations/` (`routes.py`, `models.py`, `rules.py`), `tests/test_aspirations.py`, `tests/test_time_zone.py`.

### Task 6: openapi.json

**Description:** One command writes the schema to a committed file; a test fails when the file doesn't match the app.

**Acceptance criteria:**
- [ ] `uv run python -m app.openapi` writes `openapi.json` at the repo root, and running it again changes nothing.
- [ ] `tests/test_contract.py` fails when the file is out of date, with a message naming the command.
- [ ] The file holds the six operations by their camelCase names, and `tests/test_contract.py` checks they are there.

**Verify:** `uv run pytest tests/test_contract.py`; change a model, see the test fail, regenerate, see it pass.

**Dependencies:** 2 to 5.

**Files:** `app/openapi.py`, `openapi.json`, `tests/test_contract.py`.

**Checkpoint:** every spec criterion but the docs and the front end's is met; the four checks pass.

### Task 7: Docs

**Description:** Write down what the slice added and decided.

**Acceptance criteria:**
- [ ] `README.md` and `CLAUDE.md` cover the new files, "adding a route", the `openapi.json` command and the time zone header.
- [ ] `specs/README.md` names the header in decision 9 and the rules-module and errors conventions; `specs/aspirations.md` is marked built with its open questions settled and the front-end criterion moved to #40.
- [ ] Docs-repo PR: the parent `CLAUDE.md` says the first routes are in. A comment on front-end #40 lists where the contract differs from the hand-written types.

**Verify:** the four checks; both PRs open and linked.

**Dependencies:** 1 to 6.

**Files:** `README.md`, `CLAUDE.md`, `specs/README.md`, `specs/aspirations.md`, `tasks/todo.md`; `../CLAUDE.md` (docs repo).
