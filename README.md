# goals-to-actions-api

API for Goals to Actions: Python, FastAPI and Postgres. Product docs live in the parent repo (`../docs/`); see `CLAUDE.md` for structure and rules.

So far: the database, the audit log, the generated query code, and the first routes, for aspirations (list, create, edit, reorder, retire, bring back). Routes arrive slice by slice (`specs/`).

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

The app and the tests connect to the local Postgres by default. To point them elsewhere, set `DATABASE_URL` (the app) or `TEST_DATABASE_URL` (the tests) in your environment; `example.env` shows both with their defaults. Nothing reads a `.env` file.

## Develop

```bash
uv run uvicorn app.main:app --reload   # http://localhost:8000
```

- Health: <http://localhost:8000/health>
- Interactive docs: <http://localhost:8000/docs>
- OpenAPI schema, the contract with the front end: <http://localhost:8000/openapi.json>

The schema is also committed as `openapi.json`, which the front end generates its types from. After any change to a route or an API model:

```bash
uv run python -m app.openapi   # rewrite openapi.json; a test fails while it's out of date
```

Routes that need to know what day it is (retiring an aspiration) read the phone's time zone from an `X-Time-Zone` header holding a name such as `America/Denver`. The names come from the system's time zone data; a host without it (a slim Linux container) will need the `tzdata` package, to be settled with hosting.

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
