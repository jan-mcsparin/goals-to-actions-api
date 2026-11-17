# Specs: the API

The map of the API work: twelve slices, what each depends on, the order they're built in, and what they share. One spec and one issue per slice; a spec is named by its module id.

**A spec written up front is a draft.** It gives the picture and lists what is still open. It is finalised when its plan is written (`../tasks/plan.md`, `../tasks/todo.md`), just before it's built, because earlier slices change later ones. Only [`database-foundation`](database-foundation.md) is written in full so far.

What the API is built on: [`data-model.md`](../../docs/data-model.md), [`product-rules.md`](../../docs/product-rules.md), [`flows.md`](../../docs/flows.md), and ADRs [003](../../docs/adr/0003-fastapi-postgres.md) to [012](../../docs/adr/0012-sign-in-with-a-passkey.md).

## Capability map

| # | Module id | Issue | Covers | Tables it adds | Depends on |
| --- | --- | --- | --- | --- | --- |
| 1 | [`database-foundation`](database-foundation.md) | #3 | Postgres under `podman compose`, dbmate, sqlc, the audit log, transactions that carry the user and action, tests against real Postgres | `users`, `audit_log` | — |
| 2 | [`aspirations`](aspirations.md) | #4 | Create, edit, priority order, retire and bring back | `aspirations` | 1 |
| 3 | [`goals-targets`](goals-targets.md) | #5 | The three goal types, count and amount targets, pause, resume, end, reached, reopen, go again | `goals`, `weekly_targets` | 2 |
| 4 | [`milestones-check-ins`](milestones-check-ins.md) | #6 | Ordered milestones, check-in records, "not yet" follow-ups | `milestones`, `check_ins` | 3 |
| 5 | [`tasks-week`](tasks-week.md) | #7 | Tasks and their week records; the week read; add, check off, back to bank, pull, swap, place | `tasks`, `task_weeks` | 3 |
| 6 | [`recurring-items`](recurring-items.md) | #8 | Structured schedules, create and edit, on and off | `recurring_items` | 3, 5 |
| 7 | [`week-turnover`](week-turnover.md) | #9 | Opening a week on Sunday evening and filling its bank, closing it with rollover and lapse, wrapping up by hand, the upcoming list, "Still matter?" | — (one column on `users`) | 5, 6 |
| 8 | [`planner`](planner.md) | #10 | Drafting the week onto days, once: maintenance first, the intensity cap, never a hand-placed task, never today after the first draft | — | 7 |
| 9 | [`quitting-goals`](quitting-goals.md) | #11 | Daily answers and urge ratings | `quit_days`, `urge_ratings` | 3 |
| 10 | [`delete`](delete.md) | #12 | Delete for mistakes, with what it takes along | — | 2–6, 9 |
| 11 | [`settings-sync`](settings-sync.md) | #13 | Intensity, the phone's time zone, a check that every write is safe to repeat | — | 1 |
| 12 | [`sign-in`](sign-in.md) | #14 | Replacing the one fixed user with a passkey and a session cookie (ADR-012) | passkeys, sessions, one-time codes and sign-in challenges; named in the spec | 1 |

**Build order:** 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12.

**Where the front end joins in** (shared decision 12):

| After slice | In the front end |
| --- | --- |
| Every slice from 2 | Types regenerated; the mock client compiles against them. Still running on mock data. |
| 2 | One screen wired for real, behind a switch, to prove the pipe and assumed decisions 6 to 11. |
| 4 | The Aspirations tab, an aspiration's page and a goal's page switch to the API. |
| 8 | Today, Week and the bank switch. |
| 11 | Settings, the on-device cache and the offline queue (ADR-004). |

4 and 9 need only 3, and 11 needs only 1, so any of them can move earlier if the front end wants them sooner. The path that gets a real plan onto Today is 1, 2, 3, 5, 6, 7, 8.

**Not in the map:** hosting and deployment (decided in ADR-011; they wait until the API is done, and sign-in is built before the API is first reachable), CI (checks are run by hand for now), and switching the front end to the real API (front-end issues #30 to #39).

## Shared decisions

Settled:

1. **The planner runs on the server** (ADR-008). No slice puts planning rules in a response for the phone to apply.
2. **Until `sign-in`, the API runs as one fixed user.** Every route gets the current user from one dependency, and every query takes the owner as a parameter, so sign-in changes that dependency and nothing else.
3. **Every table arrives with the full set of shared columns** (`id`, `user_id`, `created_at`, `updated_at`, `deleted_at`) **and the audit trigger**, in the migration that creates it. Every read leaves out deleted rows from the start, even though the routes that delete arrive in slice 10.
4. **A slice adds its tables, its queries, its routes and their tests together.** No migration runs ahead of the slice that uses it.
5. **Where one action spans two slices, the later slice finishes it.** Pausing a goal changes its status in slice 3; setting its tasks aside is added in slice 5, when tasks exist. Each spec lists what it leaves for later.

12. **The contract is checked against the front end after every slice; screens switch to the API at three points.** Each slice that adds endpoints ends with the front end's types regenerated and its mock client compiling against them. The app keeps running on mock data until a whole group of screens can be real, because mock rows point at each other and a half-real app needs throwaway glue. The wiring itself is front-end work, with its own issues and specs there.

Settled with Jan on 2026-11-13, and used from slice 2 on. The front end's client foundation (its issue #40) is where each is first tried from a real client; one that doesn't survive that is changed here:

6. **The device makes the id, and a create is safe to repeat.** A create is `PUT /things/{id}`: the first call creates the row, and the same call again returns the row as it is. This is what lets the phone's offline queue resend without making duplicates (ADR-004).
7. **Actions are `POST /things/{id}/action`** (`/goals/{id}/pause`), each written so that repeating it changes nothing: pausing a paused goal returns the paused goal.
8. **Two devices changing the same row: the last write wins.** No version numbers or conflict responses.
9. **The phone sends its time zone name with every request,** in the `X-Time-Zone` header (`America/Denver`). Routes that need the day refuse a request without one (422). "Today" and "this week" are worked out from it on the server. A check-off also carries the moment and the day as the phone saw them (`data-model.md`).
10. **Errors use FastAPI's shape** (`{"detail": ...}`): 404 for a row that doesn't exist or belongs to someone else, 409 for a change the rules don't allow (resuming a goal that isn't paused), 422 for a body that doesn't validate.
11. **Reads return whole screens' worth, not rows to stitch.** The week comes back with each task's goal label, not a list of ids to look up. Lists aren't paged at one user's volume.

Settled 2026-11-16 (ADR-010):

13. **The week is the only plan read.** The phone stores it as one document and draws Today, a day and the bank from it.
14. **A write the phone may queue states its end result, and its request body only changes by addition.** A plan edit also names its week. The queueable writes are listed in `tasks-week` and `quitting-goals`; every other write needs a connection.
15. **A queued write that no longer applies gets a 404 or a 409, never a 500,** so the phone can drop it. A create is never refused over where it goes. Only those two answers drop a change; the phone keeps it on any other, a 401, 403 or 422 included.

Settled 2026-11-16 (ADR-011):

16. **The API serves its routes under `/api`,** locally as well as hosted, so a request looks the same through the dev proxy and through CloudFront. The routes built so far have no prefix yet; issue #20 adds it.
17. **Hosted, each running copy of the API holds one database connection** and checks it before use. Locally the default pool stays.

## Shared conventions

Stack: Python 3.15, FastAPI, Pydantic, uv; Postgres; sqlc with `sqlc-gen-python`; dbmate; SQLAlchemy only as the connection, on psycopg 3 (ADR-007). No new dependency without asking.

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv run uvicorn app.main:app --reload
```

The database commands (`podman compose up`, dbmate, `sqlc generate`) are added by slice 1.

**Structure** (as it will be after slice 1; each slice adds files of the same kinds):

```
app/
  config.py        APP_NAME and settings read from the environment
  schemas.py       ApiModel
  main.py          the app; includes each slice's router
  database.py      the engine, transaction(), the current-user dependency
  errors.py        NotFound and NotAllowed, sent as 404 and 409
  time_zone.py     today's date from the X-Time-Zone header
  openapi.py       writes openapi.json
  db/              generated by sqlc. Never edited by hand.
  <slice>/         one folder per slice:
    routes.py        the router
    models.py        request and response models
    rules.py         rules that need more than one query; no FastAPI imports
db/
  migrations/      dbmate: one .sql file per change, with up and down
  queries/         one .sql file per table or use, annotated for sqlc
  schema.sql       written by dbmate, committed
specs/             this folder
tasks/             the plan and task list for the slice being built
tests/
```

**Code style:**

- Routes are thin: validate, open a transaction, call generated queries, return an `ApiModel`. Rules that need more than one query live in the slice's `rules.py`, with no FastAPI imports. Shared modules (`database.py`, `errors.py`) stay at the top of `app/`; database files are organised by table, not by slice.
- SQL lives only in `db/`. Lowercase keywords, one query per name, the owner in every `where`.
- API models are written by hand and extend `ApiModel`; generated row models never leave the API directly, so a column change doesn't silently change the contract.
- A route function is named for what the front end calls (`check_off_task` → `checkOffTask`).
- Status and type values are the same words in the database, in Python and in JSON, in snake_case in SQL and camelCase in JSON where they have two words (`one_off` / `oneOff`).

**Testing:**

- Every route has tests through the test client against real Postgres: the ordinary case, each rule it enforces, another user's row (404), and the same write sent twice.
- Rules that live in the database (check constraints, unique indexes, owner in foreign keys) each get one test that tries to break them.
- Each test runs in a transaction that is rolled back.
- `tests/test_contract.py` keeps guarding camelCase, `ApiModel` and operation ids across every new route.

**Boundaries:**

- **Always:** work on a branch and open a PR; run the four checks before saying work is done; update `../docs/` in the same work when behaviour or the data model changes; keep generated code generated.
- **Ask first:** any new dependency; a change to the data model in `data-model.md`; a new shared convention; anything a spec lists as an open question.
- **Never:** SQL outside `db/`; a query without the owner; reading the audit log from a route; a planner write to a hand-placed task, or to today after a week's first draft; tests against anything but Postgres.
