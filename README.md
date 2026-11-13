# goals-to-actions-api

API for Goals to Actions: Python, FastAPI and Postgres. Product docs live in the parent repo (`../docs/`); see `CLAUDE.md` for structure and rules.

This is the bare skeleton: the app, a health endpoint, and the checks. The database, migrations and generated queries (ADR-007) come next.

## Install

Needs [uv](https://docs.astral.sh/uv/) (`brew install uv`).

```bash
uv sync        # Python from .python-version, packages from uv.lock, into .venv
```

## Develop

```bash
uv run uvicorn app.main:app --reload   # http://localhost:8000
```

- Health: <http://localhost:8000/health>
- Interactive docs: <http://localhost:8000/docs>
- OpenAPI schema, the contract with the front end: <http://localhost:8000/openapi.json>

## Check

```bash
uv run ruff check .            # lint
uv run ruff format --check .   # formatting (drop --check to fix)
uv run mypy                    # types
uv run pytest                  # tests
```
