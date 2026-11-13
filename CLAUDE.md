# CLAUDE.md: goals-to-actions-api

The API for Goals to Actions. Product context, rules and ADRs live in the parent folder (`../CLAUDE.md`, `../docs/`). Read `../docs/data-model.md` before any schema or query work, and `../docs/product-rules.md` before planner work.

## Stack

Python 3.15, FastAPI, Pydantic. Packages and the virtualenv are managed by uv (`pyproject.toml`, `uv.lock`, `.python-version`).

Decided, not built yet (ADR-007):

- Postgres, run locally with `podman compose`.
- Migrations as plain SQL files with up and down, run by dbmate.
- Queries as `.sql` files; sqlc generates the Python. No ORM. SQLAlchemy is used only as the connection the generated code runs through, on psycopg 3.

## Structure

```
app/
  config.py      APP_NAME (the only place the product name appears in code)
  schemas.py     ApiModel, the base for everything the API sends or accepts
  main.py        the FastAPI app and its routes
tests/
specs/           the map of the API work (specs/README.md) and one spec per slice
```

Work is built slice by slice from `specs/`. A spec is a draft until its plan is written; read the map's shared decisions and conventions before starting a slice.

## Rules

- **The OpenAPI schema is the contract.** The front end generates its types from it, so every route declares its request and response models.
- **JSON is camelCase, Python is snake_case.** Every API model extends `ApiModel`, which does the aliasing. Don't alias fields by hand. `tests/test_contract.py` fails if a snake_case property reaches the schema.
- **An operation is named after its route function,** in camelCase (`check_off_task` becomes `checkOffTask`), because generated clients take their function names from it. Give route functions the name the front end should call.
- **Ask before adding a dependency.**
- **Days, moments and times are stored three ways** (`date`, `timestamptz` in UTC, `time`), never with an offset. See `../docs/data-model.md`.
- **History:** if a feature reads it, it's a table or column; everything else is the audit log (ADR-005). Nothing reads the audit log.
- Write or update tests with every behavior change. Tests that touch the database run against real Postgres, never SQLite.
- Update `../docs/` in the same piece of work when behavior or the data model changes.

## Checks

Run all four before saying work is done:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```
