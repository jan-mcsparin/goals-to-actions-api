# Tasks: Database foundation (#3)

Plan: [`plan.md`](plan.md). Spec: [`../specs/database-foundation.md`](../specs/database-foundation.md).

Every task: write the tests first where there is behaviour to test, run the four checks (`uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run pytest`), then one commit.

# PR: `database-foundation` (closes #3)

### Task 1: Postgres under compose

**Description:** `compose.yaml` with `postgres:18`, a named volume at `/var/lib/postgresql`, port 5432 and a health check. `.env.example` with the development and test URLs.

**Acceptance criteria:**
- [x] `podman compose up -d` starts Postgres and it reports healthy.
- [x] Data survives `podman compose down` and `up` again.
- [x] ~~`.env.example` is committed~~ Dropped: a permission rule blocks writing `.env*` files. The app defaults to the local URLs instead (task 5), and the README lists them (task 7).

**Verify:** `podman compose up -d`, then `podman compose exec db psql -U <user> -c 'select version()'` shows 18; down, up, a table created before is still there.

**Files:** `compose.yaml`, `.env.example`.

### Task 2: dbmate and the audit migration

**Description:** A `dbmate` compose service and `bin/dbmate` (with `--test`). The first migration: `audit_log`, the `audit()` trigger function, the `set_updated_at()` function, each with a down.

**Acceptance criteria:**
- [x] `bin/dbmate up`, `status` and `rollback` work against the development database; `bin/dbmate --test up` creates and migrates the test database.
- [x] `db/schema.sql` is written by `up` and committed; `--test` doesn't touch it.
- [x] `up`, `rollback`, `up` leaves `schema.sql` unchanged.

**Found:** the dbmate image's `pg_dump` (18.6) writes `pg_attver=<n>` lines that change on every run. `bin/dbmate` dumps with the Postgres container's own `pg_dump` (18.7) instead, which doesn't.

**Verify:** the commands above; `git diff --stat db/schema.sql` empty after the round trip.

**Files:** `compose.yaml`, `bin/dbmate`, `db/migrations/<ts>_audit.sql`, `db/schema.sql`.

**Checkpoint:** report whether the image's `pg_dump` worked against Postgres 18.

### Task 3: The users table and the fixed user

**Description:** The second migration: `users` as in the spec, its `updated_at` and audit triggers, and the fixed user. The fixed user's id in `app/config.py`.

**Acceptance criteria:**
- [x] `users` exists with the check on intensity; the fixed user is there with intensity `normal`.
- [x] Inserting the fixed user wrote one audit row, with no user and no action.
- [x] `up`, `rollback`, `up` works and leaves `schema.sql` unchanged.

**Verify:** `bin/dbmate up`; `psql` shows the user and its audit row; the round trip.

**Files:** `db/migrations/<ts>_users.sql`, `db/schema.sql`, `app/config.py`.

### Task 4: sqlc and the users queries

**Description:** `sqlc.yaml` (plugin 1.3.0 by URL and hash, schema `db/migrations`, queries `db/queries`, out `app/db`, sync querier, Pydantic models). `db/queries/users.sql`: get a user, set intensity, set time zone, set planned-through week. Add `sqlalchemy` and `psycopg[binary]`. Leave `app/db/` out of ruff.

**Acceptance criteria:**
- [x] `sqlc generate` writes `app/db/` from the migrations as they are, triggers and functions included.
- [x] `sqlc diff` is clean; the generated code is committed.
- [x] mypy strict passes over `app/db/` with no ignores.
- [x] The generated types for the UUID, the date, the nullable columns and `intensity` are written down for the ADR.

**Found (for ADR-007), sqlc 1.31.1, sqlc-gen-python 1.3.0, SQLAlchemy 2.1.8, psycopg 3.3.9:**
- sqlc reads the dbmate migrations as they are: up/down markers, `create function` (plpgsql) and `create trigger` all parse.
- `uuid` → `uuid.UUID`; `date` → `datetime.date`; `timestamptz` → `datetime.datetime`, which arrives aware (UTC); `jsonb` → `Any`.
- Nullable columns and parameters are `Optional[...]`; passing `None` sets a column back to empty.
- `intensity` (text with a check) is plain `str`. The API model narrows it with a `Literal`.
- Each query gets its own row model even when the columns are the same (`GetUserRow`, `SetIntensityRow`, ...). Parameters are keyword-only.
- The generated code passes mypy strict with no ignores; it's excluded from ruff, whose style it doesn't follow. No `__init__.py` is generated; `app.db` works as a namespace package.

**Verify:** `sqlc generate && sqlc diff`; the four checks.

**Files:** `sqlc.yaml`, `db/queries/users.sql`, `app/db/*`, `pyproject.toml`, `uv.lock`.

**Checkpoint:** report ADR-007's checks to Jan. Stop if any failed.

### Task 5: Connections, the test setup and query tests

**Description:** `app/database.py`: the engine from `DATABASE_URL`, the connection provider, `transaction(user_id, action)`, a read connection, the current-user dependency. `tests/conftest.py`: a connection to the test database inside a rolled-back transaction, connecting only when asked for. Tests for the generated queries and the fixed user.

**Acceptance criteria:**
- [x] Tests: get the fixed user; set intensity, time zone and planned-through week and read them back; set a nullable value back to empty.
- [x] Test: the current-user dependency returns the fixed user's id.
- [x] Nothing a test writes is left in the test database.
- [x] The eight existing tests pass with Postgres stopped.

**Built as:** `Database(bind)` holds the provider, so `transaction()` and `read()` are its methods: `database.transaction(user_id, action)`. Bound to the engine, a transaction is `engine.begin()` and a read is a read-only connection (a test proves Postgres refuses a write through it). Bound to a test's connection, a transaction is a savepoint. Routes get it from the `get_database` dependency, which tests override. `DATABASE_URL` and `TEST_DATABASE_URL` default to the local compose URLs.

**Verify:** the four checks with Postgres up; `uv run pytest tests/test_health.py tests/test_schemas.py tests/test_contract.py` with it down.

**Files:** `app/database.py`, `app/config.py`, `tests/conftest.py`, `tests/test_users_queries.py`, `tests/test_database.py`.

### Task 6: Audit, updated_at and constraints

**Description:** The tests that prove the database rules, and whatever they show is missing.

**Acceptance criteria:**
- [x] An insert, an update and a delete each write one audit row with the right operation, before and after.
- [x] A write inside `transaction()` carries its user and action.
- [x] A second transaction on the same pooled connection doesn't inherit them (the one test that commits; it restores what it changed).
- [x] `audit_log` isn't audited.
- [x] `updated_at` moves on update without the query setting it; `created_at` doesn't.
- [x] An intensity outside the three is refused by the database.

**Checked by breaking:** dropping the audit trigger fails the five audit tests; dropping the `updated_at` trigger fails its test; `set_config(..., false)` fails the pooled-connection test. No gap found, so no migration or code changed. The committing test leaves the fixed user's `updated_at` moved; everything else is put back.

**Verify:** the four checks; break each rule by hand once (drop the trigger in a scratch migration, see the test fail, put it back).

**Files:** `tests/test_audit.py`, `tests/test_users_table.py`, and `app/database.py` or a migration if a test finds a gap.

### Task 7: Docs

**Description:** `README.md` (setup from a fresh clone, the database commands), `CLAUDE.md` (structure, how a slice adds a table, "decided, not built yet" becomes built). In the docs repo, its own PR: a dated "Revisited" section on ADR-007 with what each check found, and the parent `CLAUDE.md` and `README.md` no longer saying "no database yet". Mark the spec built.

**Acceptance criteria:**
- [ ] Following the README on a fresh clone brings up Postgres, migrates both databases and runs the tests.
- [ ] ADR-007 records each check, with `numeric` marked as answered in `tasks-week`.
- [ ] Every success criterion in the spec is ticked, or the PR says why not.

**Verify:** a fresh clone in the scratchpad, following the README word for word.

**Files:** `README.md`, `CLAUDE.md`, `specs/database-foundation.md`; docs repo: `docs/adr/0007-data-access-and-migrations.md`, `CLAUDE.md`, `README.md`.
