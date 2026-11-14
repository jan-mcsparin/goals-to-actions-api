# goals-to-actions-api

API for Goals to Actions: Python, FastAPI and Postgres. Product docs live in the parent repo (`../docs/`); see `CLAUDE.md` for structure and rules.

So far: the app, a health endpoint, the database (the `users` and `audit_log` tables), the generated query code, and the checks. Routes arrive slice by slice (`specs/`).

## Install

Needs [uv](https://docs.astral.sh/uv/), [Podman](https://podman.io/) with `podman compose`, and [sqlc](https://sqlc.dev/) (`brew install uv podman docker-compose sqlc`).

```bash
uv sync                     # Python from .python-version, packages from uv.lock, into .venv
podman machine init         # once, if there's no Podman machine yet
podman machine start
podman compose up -d --wait # Postgres 18 on localhost:5432
bin/dbmate up               # migrate the development database (and write db/schema.sql)
bin/dbmate --test up        # create and migrate the test database
```

The app and the tests connect to the local Postgres by default. To point them elsewhere, set `DATABASE_URL` (the app) or `TEST_DATABASE_URL` (the tests):

```
DATABASE_URL=postgresql+psycopg://gta:gta@localhost:5432/gta_dev
TEST_DATABASE_URL=postgresql+psycopg://gta:gta@localhost:5432/gta_test
```

These credentials are for the local container only.

## Develop

```bash
uv run uvicorn app.main:app --reload   # http://localhost:8000
```

- Health: <http://localhost:8000/health>
- Interactive docs: <http://localhost:8000/docs>
- OpenAPI schema, the contract with the front end: <http://localhost:8000/openapi.json>

## Database

```bash
podman compose up -d --wait    # start Postgres; data is kept in a named volume
podman compose down            # stop it (data stays)
bin/dbmate new <name>          # a new migration in db/migrations/
bin/dbmate up                  # apply pending migrations; rewrites db/schema.sql
bin/dbmate rollback            # undo the latest migration
bin/dbmate status              # what's applied
bin/dbmate --test up           # the same, against the test database (schema.sql untouched)
sqlc generate                  # regenerate app/db/ from db/migrations/ and db/queries/
sqlc diff                      # fails if app/db/ is out of date
```

`bin/dbmate` runs dbmate in its container on the compose network, then dumps `db/schema.sql` with the Postgres container's own `pg_dump`. Commit `db/schema.sql` and `app/db/` with the change that produced them.

## Check

```bash
uv run ruff check .            # lint
uv run ruff format --check .   # formatting (drop --check to fix)
uv run mypy                    # types
uv run pytest                  # tests; the database tests need Postgres up and the test database migrated
```
