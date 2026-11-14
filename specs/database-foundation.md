# Spec: Database foundation

Status: built 2026-11-13; plan in [`../tasks/plan.md`](../tasks/plan.md). Issue: [#3](https://github.com/jan-mcsparin/goals-to-actions-api/issues/3). Module `database-foundation` in the [map](README.md). Depends on nothing; every other slice depends on it.

## Objective

Give the API a database it can be built on: Postgres running locally, migrations that go up and down, query code generated from SQL, the audit log working from the first table, and tests that run against real Postgres. After this slice, adding a feature means adding a migration, a query file and a route, with no plumbing left to invent.

It also answers what ADR-007 left to confirm on the first database work, so the later specs can be written against facts.

No route is added and nothing the front end can call changes.

References: [ADR-005](../../docs/adr/0005-history.md), [ADR-007](../../docs/adr/0007-data-access-and-migrations.md), [`data-model.md`](../../docs/data-model.md) (On every table, users, audit_log).

### What exists afterwards

1. **Postgres under `podman compose`,** on the current major version, pinned. One server with two databases: one for development, one for tests.
2. **dbmate, run from its container image,** with `db/migrations/` and a committed `db/schema.sql`. Up, down and status are each one documented command.
3. **sqlc with `sqlc-gen-python`,** reading the migrations as its schema and `db/queries/` as its queries, writing Pydantic row models and typed query methods to `app/db/`.
4. **The `users` table:** `id`, `intensity` (`going_hard`, `normal`, `easing_off`; default `normal`), `time_zone` (a zone name, empty until the phone sends one), `planned_through_week` (a date, empty at first), `created_at`, `updated_at`, `deleted_at`. No `user_id`: the row is its own owner.
5. **The one fixed user,** created by a migration with a fixed id that `app/config.py` also holds. A dependency returns it as the current user; `sign-in` later replaces that dependency.
6. **`updated_at` is kept by a trigger,** so no query can forget it.
7. **The `audit_log` table and one trigger function,** attached to `users` here and to every later table in the migration that creates it. Each insert, update and delete writes the table, the row id, the operation, the row before and after as JSON, the user, the action and the time.
8. **`transaction(user_id, action)`,** the only way application code writes. It opens a transaction and sets the user and the action for that transaction only, which is where the audit trigger reads them. A write made outside it (a migration, the seeded user) is audited with no user and no action.
9. **A test setup:** the test database is migrated by the same dbmate command, and each test runs inside a transaction that is rolled back.

## Scope

**In:**

- `compose.yaml`, `example.env` (the local connection strings, which are also the defaults). Named `example.env`, not `.env.example`, because a permission rule blocks writing `.env*` files.
- `db/migrations/` with two migrations: the audit log, trigger function and `updated_at` function; then `users` with its triggers and the fixed user.
- `db/queries/users.sql`: get a user, set intensity, set time zone, set planned-through week. Enough to exercise every column type the table has.
- `sqlc.yaml`; generated `app/db/`, committed.
- `app/database.py`: the engine, `transaction()`, a read-only connection for reads, the current-user dependency.
- `app/config.py`: the database URL from the environment, the fixed user's id.
- Dependencies `sqlalchemy` and `psycopg` (both already approved).
- `README.md` and `CLAUDE.md`: the new commands, the structure, and how a slice adds a table.
- `docs/adr/0007-data-access-and-migrations.md` in the docs repo: a dated "Revisited" section with what the four checks found.

**Out (later):**

- Any route, including reading or changing settings (`settings-sync`).
- Any other table.
- Async queries, a connection pool tuned for production, hosting.
- CI. The checks, the migrations and `sqlc generate` are run by hand.
- Row-level security (waits for a second user, ADR-007).

## ADR-007's four checks

Each gets an answer written into ADR-007, and a test where one is possible.

| Check | How this slice answers it |
| --- | --- |
| How UUIDs, dates and nullable parameters are typed | `users` has all three. The generated signatures are read, and mypy runs strict over code that calls them. |
| How `numeric` is typed | **Not answered here:** `users` has no number column. It's answered in `tasks-week` (the value logged on a task). |
| Whether text-with-check columns come out as plain `str`, and whether that's good enough | `intensity` is one. If it is `str`, the API model narrows it with a `Literal`, and the spec for slice 2 says whether that's enough. |
| That the per-transaction setting works through SQLAlchemy's connection | A test writes inside `transaction()` and reads the audit row's user and action, then checks a second transaction on the same pooled connection doesn't inherit them. |
| That sqlc reads dbmate migration files as its schema | `sqlc generate` runs against `db/migrations/` with dbmate's up and down markers in the files. |

If a check fails, stop and bring it back before working round it: the fallbacks (generate from `schema.sql`, hand-written mapping on psycopg) are decisions, not fixes.

## Commands

The four checks in the [shared conventions](README.md#shared-conventions), plus these. Exact flags are settled in the plan against each tool's documentation.

```bash
podman compose up -d          # start Postgres
podman compose down           # stop it; the data stays in a named volume
<dbmate> up                   # apply migrations to the development database, rewrite db/schema.sql
<dbmate> rollback             # undo the latest migration
<dbmate> status
sqlc generate                 # rewrite app/db/ from db/migrations and db/queries
sqlc diff                     # fails if app/db/ is out of step with the SQL
```

`<dbmate>` is a short wrapper (a compose service or a script) round the dbmate image, so nobody types the full `podman run` line. The test database is migrated by the same wrapper pointed at the test URL.

## Code style

A sketch of each kind of file. The generated names and exact options are confirmed in the plan.

```sql
-- db/migrations/20261114000002_users.sql
-- migrate:up
create table users (
    id uuid primary key,
    intensity text not null default 'normal'
        check (intensity in ('going_hard', 'normal', 'easing_off')),
    time_zone text,
    planned_through_week date,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    deleted_at timestamptz
);
create trigger users_set_updated_at before update on users
    for each row execute function set_updated_at();
create trigger users_audit after insert or update or delete on users
    for each row execute function audit();

-- migrate:down
drop table users;
```

```sql
-- db/queries/users.sql
-- name: GetUser :one
select id, intensity, time_zone, planned_through_week, created_at, updated_at
from users
where id = $1 and deleted_at is null;

-- name: SetIntensity :one
update users set intensity = $2
where id = $1 and deleted_at is null
returning id, intensity, time_zone, planned_through_week, created_at, updated_at;
```

```python
# app/database.py
@contextmanager
def transaction(user_id: UUID, action: str) -> Iterator[Connection]:
    """The only way application code writes: one transaction, audited as this user doing this action."""
    with engine.begin() as connection:
        connection.execute(SET_AUDIT_CONTEXT, {"user_id": str(user_id), "action": action})
        yield connection
```

Actions are named as the person would say them, lowercase: "set intensity", "pause goal". The audit trigger function is written once and takes no arguments; it reads the table name from the trigger itself.

## Testing strategy

All against the test database, each test rolled back.

- **Audit:** an insert, an update and a delete each write one audit row with the right operation, before and after; a write inside `transaction()` carries its user and action; a later transaction doesn't inherit them; `audit_log` itself isn't audited.
- **`updated_at`:** moves on update without the query setting it; `created_at` doesn't.
- **Constraints:** an intensity outside the three is refused by the database.
- **Generated queries:** get the fixed user; set intensity, time zone and planned-through week and read them back, including setting a nullable value back to empty.
- **The fixed user:** exists after migrating, with intensity `normal`; the current-user dependency returns its id.
- **Typing:** mypy strict passes over the tests that call the generated code, with no `type: ignore`.
- **By hand, recorded in the PR:** `up`, `rollback`, `up` again on an empty database leaves the same `schema.sql`; `sqlc diff` is clean; the existing eight tests still pass with Postgres stopped (they don't need it) or the README says they now do.

## Boundaries

- **Always:** every table gets the audit trigger and the `updated_at` trigger in the migration that creates it; every migration has a working down; generated code is committed and matches the SQL.
- **Ask first:** any dependency beyond `sqlalchemy` and `psycopg`; any Postgres extension; changing a convention in ADR-007; a fallback if one of the four checks fails.
- **Never:** edit `app/db/` by hand; write from application code outside `transaction()`; put a real password or a hosted database URL in the repo; run the tests against the development database.

## Success criteria

- [x] On a fresh clone, the README's steps bring up Postgres, migrate both databases and run the tests.
- [x] `users` and `audit_log` exist as described, and the fixed user is there.
- [x] `sqlc generate` produces `app/db/` from the migrations and `db/queries/users.sql`, and `sqlc diff` is clean.
- [x] Every test above exists and passes; ruff, format, mypy and pytest pass.
- [x] Rolling back both migrations and applying them again works.
- [x] ADR-007 records what each of the four checks found, with `numeric` marked as answered in `tasks-week`.
- [x] `README.md` and `CLAUDE.md` describe the new commands and structure, and the docs repo no longer says "no database yet". (ADR-007 and the docs repo: jan-mcsparin/goals-to-actions#17.)

## Settled with Jan, 2026-11-13

1. **This slice adds no route.** It is plumbing, proved by tests. Slice 2 is the first route.
2. **The fixed user is created by a migration,** with the same id in every environment until sign-in.
3. **sqlc downloads `sqlc-gen-python`** from the URL in `sqlc.yaml`, checked against a pinned hash. The plugin file isn't kept in the repo.
