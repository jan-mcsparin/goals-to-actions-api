# Tasks: Settings and sync (#13)

Plan: [`plan.md`](plan.md). Spec: [`../specs/settings-sync.md`](../specs/settings-sync.md).

Every task: write the tests first, run the four checks (`uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run pytest`), then one commit.

# PR: `settings-sync` (closes #13)

### Task 1: Read and set intensity

**Description:** `getSettings`, `GET /api/settings`, and `setIntensity`, `PUT /api/settings/intensity`, both returning `Settings`. A new `app/settings/` slice; the queries exist.

**Acceptance criteria:**
- [x] A new user reads Normal; setting Going hard is read back, and the week read marks days against cap 6. Nothing is placed or moved.
- [x] An unknown intensity is a 422; setting it twice gives the same answer and changes nothing more; the audit log names "set intensity".
- [x] Values are camelCase in JSON, snake_case in the database.

**Verify:** `uv run pytest tests/test_settings.py`, then the four checks.

**Dependencies:** none.

**Files:** `app/settings/{__init__,routes,models}.py`, `app/main.py`, `tests/test_settings.py`, `openapi.json`.

**Scope:** S

### Task 2: The time zone follows the phone

**Description:** `today()` saves the header's zone on the user when it differs from the stored one.

**Acceptance criteria:**
- [x] A request with `X-Time-Zone: Asia/Tokyo` leaves Tokyo on the user; a later one from Denver leaves Denver.
- [x] A second request from the same zone writes nothing (no audit row).
- [x] A name that isn't a zone is refused (422) and nothing is saved.

**Verify:** `uv run pytest tests/test_time_zone.py`, then the four checks.

**Dependencies:** none.

**Files:** `app/turnover/dependencies.py`, `tests/test_time_zone.py`.

**Scope:** S

## Checkpoint: after task 2

- [x] The four checks pass.

### Task 3: Repeat test, first half

**Description:** `tests/test_repeats.py`: the table, the twice-and-compare test, the row snapshot; rows for every aspiration, goal, weekly target, milestone and check-in write.

**Acceptance criteria:**
- [x] Each of those writes, sent twice, gives the same status and body and leaves the same rows.
- [x] Any write found unsafe is fixed in its own commit with a test, or raised.

**Verify:** `uv run pytest tests/test_repeats.py`, then the four checks.

**Dependencies:** 1.

**Files:** `tests/test_repeats.py`.

**Scope:** M

### Task 4: Repeat test, second half, and every write covered

**Description:** Rows for quitting, recurring item, task, week and settings writes; a test that every write operation in the schema has a row.

**Acceptance criteria:**
- [x] Each of those writes passes the repeat test.
- [x] The coverage test fails if a write operation in `openapi.json` has no row.

**Verify:** `uv run pytest tests/test_repeats.py`, then the four checks.

**Dependencies:** 3.

**Files:** `tests/test_repeats.py`.

**Scope:** M

### Task 5: Queued writes that no longer apply

**Description:** `tests/test_queued_writes.py` over the ten queueable writes.

**Acceptance criteria:**
- [ ] Each, aimed at a deleted row, answers 404 or 409; the task writes also against a set-aside task and a week the task has left.
- [ ] `addTask` onto a past day, or today when today is before the current week, lands in the current week's bank.
- [ ] Two devices updating one task: the last to arrive wins, whatever moment either phone saw.

**Verify:** `uv run pytest tests/test_queued_writes.py`, then the four checks.

**Dependencies:** 4.

**Files:** `tests/test_queued_writes.py`.

**Scope:** M

## Checkpoint: after task 5

- [ ] The four checks pass.

### Task 6: What the queue can rely on; docs, the contract and the front end's types

**Description:** A README section for the front end: the queueable writes, sent one at a time in order, what each answer means (success; 404 or 409 dropped; anything else kept and retried), bodies change only by addition. Mark the spec and map; update `../docs/` where it describes settings or the time zone; regenerate `openapi.json`; in the front end, `npm run api:types` on a branch, check its build and tests, and open its PR.

**Acceptance criteria:**
- [ ] The README section exists and matches the tests in tasks 4 and 5.
- [ ] The spec's success criteria are checked; `CLAUDE.md`'s structure lists `settings/`.
- [ ] The front end's types are regenerated; its build, lint and tests pass.

**Verify:** the four checks; in `web-frontend/`, `nvm use`, `npm run build`, `npm run lint`, `npm test`.

**Dependencies:** 5.

**Files:** `README.md`, `CLAUDE.md`, `specs/{settings-sync,README}.md`, `../docs/data-model.md` (if needed), `openapi.json`; in the front end, `src/api/openapi.ts`.

**Scope:** M

## Checkpoint: after task 6

- [ ] The slice is done; the front end compiles against the new types.
