# goals-to-actions-api

API for Goals to Actions: Python, FastAPI and Postgres. Product docs live in the parent repo (`../docs/`); see `CLAUDE.md` for structure and rules.

Built slice by slice (`specs/`): the database and the audit log, aspirations, goals, milestones, tasks and the week, recurring items, week turnover and the planner, quitting goals, delete, settings, and sign-in.

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

- Health: <http://localhost:8000/api/health>
- Interactive docs: <http://localhost:8000/api/docs>
- OpenAPI schema, the contract with the front end: <http://localhost:8000/api/openapi.json>

Every route is served under `/api`, here as well as hosted, because CloudFront passes `/api/*` to the API with the path unchanged (ADR-011). The front end's dev proxy passes the path on as it is.

The schema is also committed as `openapi.json`, which the front end generates its types from. After any change to a route or an API model:

```bash
uv run python -m app.openapi   # rewrite openapi.json; a test fails while it's out of date
```

Routes that need to know what day it is (retiring an aspiration) read the phone's time zone from an `X-Time-Zone` header holding a name such as `America/Denver`, and keep it on the user as last known. A name that isn't a zone is refused (422). The names come from the system's time zone data; a host without it (a slim Linux container) will need the `tzdata` package, to be settled with hosting.

## Sign-in

Every route but `health` and `/api/sign-in/*` answers 401 without a session ([ADR-012](../docs/adr/0012-sign-in-with-a-passkey.md)). A session is a `__Host-session` cookie (`HttpOnly`, `Secure`, `SameSite=Lax`) that lasts 90 days from its last use. Any write (`POST`, `PUT`, `PATCH`, `DELETE`) whose `Origin` isn't `APP_ORIGIN` is a 403.

There's no sign-up. A user is added by a command, which prints their first one-time code (used once, for ten minutes); typed into the app, it lets that device add a passkey. The same command makes a new code for a new device, or to get back in:

```bash
uv run python -m app.sign_in.command add-user                  # a new user, and their first code
uv run python -m app.sign_in.command code <user-id>            # a new code for a user
uv run python -m app.sign_in.command end-sessions <user-id>    # a lost phone: signed out everywhere
uv run python -m app.sign_in.command remove-passkeys <user-id> # no longer trusted: signed out, and only a new code gets them back
```

Signing in again on a device ends that device's earlier session.

Hosted, it runs inside AWS against the hosted database. The founder's account is the user from before sign-in (`FIXED_USER_ID`), so to sign in locally the first time: `uv run python -m app.sign_in.command code 00000000-0000-4000-8000-000000000001`.

Two settings, from the environment:

- `APP_ORIGIN`: the app's own origin. Defaults to the dev server, `http://localhost:5173`.
- `PASSKEY_RP_ID`: the name passkeys are bound to. Defaults to `localhost`; hosted, `goals-to-actions.jan-mcsparin.me`.

Passkeys need `localhost` or HTTPS on a real name, so locally sign in on the laptop at `http://localhost:5173`. Chrome and Firefox keep a `Secure` cookie on `http://localhost`; Safari may not. A phone pointed at the laptop's address can't sign in: the installed app is tried against the hosted API.

The passkey steps (`redeemCode`, `addPasskey`, `startSignIn`, `finishSignIn`) work once by design, since a code and a challenge are spent, so they aren't in the repeat test. `signOut` is. Tests make a session row directly and stand in for the library's passkey check.

## What the offline queue can rely on

For the front end's cache and queue ([ADR-004](../docs/adr/0004-instant-open.md), [ADR-010](../docs/adr/0010-week-document-and-replayed-queue.md)). Each point is held by a test that runs over the whole API.

- **The queueable writes** are `addTask`, `checkOffTask`, `uncheckTask`, `placeTask`, `moveTaskToBank`, `swapTasks`, `answerQuitDay`, `clearQuitDay`, `rateUrge` and `clearUrgeRating`. Every other write needs a connection.
- **Send them one at a time, in order,** the next only after the last is answered.
- **What each answer means:**
  - 2xx: it landed. It leaves the queue.
  - 404 or 409: it no longer applies (its task, goal or day is gone, or the task has left the week the edit names). Drop it.
  - Anything else (a 401, 403 or 422, a server error, no answer): keep it, stop sending, try again later.
- **Every write is safe to send twice,** queueable or not: the second send gives the same answer and leaves the same data (`tests/test_repeats.py`, which fails for a new write without a case).
- **A late write never ends in a 500** (`tests/test_queued_writes.py`). Aimed at a deleted task or goal it's a 404, or a 409 for an `addTask` resent after its task was deleted. A plan edit aimed at a set-aside task, or naming a week the task has left, is a 409. A check-off of a set-aside task still lands: done is done.
- **A create is never refused over where it goes.** A task added to a day no longer allowed (a past day, or today after a wrap-up) is saved in the current week's bank.
- **Two devices changing one row: the last write to arrive wins.** No versions, no conflict answers. The server never orders writes by the phone's clock.
- **A queueable write's request body only changes by addition,** so a change queued by an older version of the app still sends.
- When the queue empties, fetch the week again (`getWeek`); it's the only plan read.

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
