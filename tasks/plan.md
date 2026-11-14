# Implementation Plan: Database foundation (#3)

Spec: [`../specs/database-foundation.md`](../specs/database-foundation.md). Tasks: [`todo.md`](todo.md).

## Overview

Postgres under `podman compose`, dbmate migrations, sqlc-generated query code, the `users` and `audit_log` tables, `transaction()` carrying the user and action to the audit trigger, and tests against real Postgres. No route. ADR-007's open checks are answered along the way and written into the ADR.

One PR, `database-foundation` (closes #3), plus a docs-repo PR linked from it.

## Checked against the tools' documentation, 2026-11-13

| Fact | Source | What it means here |
| --- | --- | --- |
| Postgres 18 is the current major (18.7); 19 is at release candidate | Docker Hub `postgres` | Pin `postgres:18`. |
| From 18, the image's volume is `/var/lib/postgresql`, not `/var/lib/postgresql/data` | Docker Hub `postgres` | Mount the named volume there, or the data is lost on restart. |
| dbmate's image is `ghcr.io/amacneil/dbmate`; `up` creates the database if it's missing | dbmate README | No init script: `up` against the test URL creates the test database. |
| dbmate needs `?sslmode=disable` for a local server | dbmate README | In both URLs. |
| dbmate writes `schema.sql` with `pg_dump`, and skips it silently if `pg_dump` is missing | dbmate README | Task 2 checks the file is really written. See Risks. |
| sqlc reads dbmate migrations, ignores the down sections, and reads files in name order | sqlc docs | `schema: db/migrations`. dbmate's timestamp names sort correctly. |
| `sqlc-gen-python` 1.3.0: wasm URL and sha256 in its README; options `package`, `emit_sync_querier`, `emit_async_querier`, `emit_pydantic_models`, `emit_str_enum` | plugin README | Sync querier and Pydantic models on; async off. |

Not answered by the documentation, so found out by running it: whether sqlc accepts `create function` and `create trigger` in the schema it reads, and whether the dbmate image's `pg_dump` is new enough for Postgres 18.

## Dependency graph

```
1 Postgres under compose
      │
      ▼
2 dbmate wrapper + migration 1 (audit_log, audit(), set_updated_at())
      │
      ▼
3 migration 2 (users, its triggers, the fixed user)
      │
      ▼
4 sqlc: config, users queries, generated app/db/      ◄── checkpoint: ADR-007's checks
      │
      ▼
5 app/database.py + test setup + query tests
      │
      ▼
6 audit, updated_at and constraint tests
      │
      ▼
7 docs: README, CLAUDE.md, ADR-007 (docs PR), spec marked built
```

Strictly in order. Each task leaves the four checks passing.

## Architecture decisions

- **dbmate is a compose service,** not a `podman run` line. It sits on the compose network and reaches Postgres as `db`, which avoids host networking through the Podman machine. A small `bin/dbmate` script wraps `podman compose run --rm dbmate "$@"`; `bin/dbmate --test ...` points it at the test database and adds `--no-dump-schema`, so only the development database writes `db/schema.sql`.
- **Two databases on one server:** `gta_dev` and `gta_test`. dbmate `up` creates each.
- **Local credentials are in `compose.yaml` and `.env.example`,** and are for the local container only. `.env` is already ignored.
- **Configuration is read from the environment with `os.environ`.** No settings library; that would be a new dependency.
- **`psycopg` is installed as `psycopg[binary]`,** so nothing has to be compiled locally. The 3.15 trial already installed and imported it.
- **`audit()` is one function for every table.** It reads the table from `TG_TABLE_NAME`, the row id from `id`, and the user and action from `current_setting('app.user_id', true)` and `current_setting('app.action', true)`, which are empty outside `transaction()`.
- **`audit_log` has its own identity key and no shared columns.** It is the one table the device never writes and nothing ever updates.
- **`transaction()` sets the audit context with `set_config(..., true)`,** which lasts for that transaction only.
- **Generated code lives in `app/db/` and is left out of ruff.** mypy still checks it. If generated code fails strict mypy, that is a finding for the checkpoint, not something to silence.
- **Test isolation:** a fixture gives each test a connection inside a transaction that is rolled back. Application code gets its connection through one provider that tests override, and `transaction()` opens a savepoint when it is handed a connection already in a transaction.
- **One test commits for real:** the check that a second transaction on the same pooled connection doesn't inherit the first one's user and action. Savepoints can't show that. It uses the real engine against the test database and puts back what it changed.
- **The existing eight tests keep running without Postgres.** The database fixture connects only when a test asks for it. A test that asks while Postgres is down fails with a message naming `podman compose up -d`.

## Risks

| Risk | If it happens |
| --- | --- |
| The dbmate image's `pg_dump` is older than Postgres 18, so `schema.sql` isn't written | Dump with the Postgres container's own `pg_dump` from `bin/dbmate`. Small, and stays inside the slice. |
| sqlc can't parse the trigger or function statements in the migrations | Stop at the checkpoint. The fallbacks (point sqlc at `schema.sql`, or keep functions in files sqlc doesn't read) change ADR-007's "sqlc reads the migrations", so they are Jan's call. |
| Generated code doesn't pass strict mypy, or doesn't run on Python 3.15 | Stop at the checkpoint with the errors. |
| The generated types are loose (`Any` for UUID or date, `Optional` handled oddly) | Recorded in ADR-007; whether to wrap or override is decided before slice 2. |
| A nullable parameter can't be set back to empty through a generated query | Recorded; affects how later slices write "clear this field". |

## Checkpoints

- **After task 2:** migrations go up and down, and `schema.sql` is written. If the `pg_dump` fallback was needed, say so.
- **After task 4:** report what ADR-007's checks found, with the generated signatures, before building on them. Stop here if any failed.
- **After task 6:** every spec criterion but the docs is met; the four checks pass.

## Verification

Every task: the four checks (`ruff check`, `ruff format --check`, `mypy`, `pytest`). Tasks 2 and 3 also: `up`, `rollback`, `up` leaves `schema.sql` unchanged. From task 4: `sqlc diff` is clean.
