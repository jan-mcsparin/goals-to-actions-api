# Implementation Plan: Aspirations (#4)

Spec: [`../specs/aspirations.md`](../specs/aspirations.md). Tasks: [`todo.md`](todo.md).

## Overview

The `aspirations` table and six routes: list, create, edit, reorder, retire, bring back. It is the first route through the whole stack, so it also adds what every later slice reuses: a test client on the rolled-back connection, the 404 and 409 errors, the time zone header, and a committed `openapi.json` with a test that fails when it's out of date.

One PR, `aspirations` (closes #4), plus a small docs-repo PR linked from it.

## The contract

| Operation | Route | Body | Returns |
| --- | --- | --- | --- |
| `listAspirations` | `GET /aspirations` | | `{ "aspirations": [...] }`: active by position, then retired, newest retirement first |
| `createAspiration` | `PUT /aspirations/{id}` | `name`, `why` (optional) | the aspiration; goes last among the active |
| `updateAspiration` | `PATCH /aspirations/{id}` | `name`, `why` | the aspiration |
| `reorderAspirations` | `POST /aspirations/reorder` | `ids`: every active id, in the new order | the same shape as the list |
| `retireAspiration` | `POST /aspirations/{id}/retire` | | the aspiration |
| `bringBackAspiration` | `POST /aspirations/{id}/bring-back` | | the aspiration; goes last |

An aspiration in JSON: `id`, `name`, `why`, `status` (`active` or `retired`), `position`, `retiredOn`, `createdAt`. `why`, `position` and `retiredOn` are `null` when empty.

- **The list is wrapped in an object** so goal counts can join it in `goals-targets` without changing its shape (open question 2: this slice returns aspirations alone).
- **`updateAspiration` sends both fields every time.** `why: null` empties it. It works on a retired aspiration too.
- **A name is trimmed and can't be blank** (422). An empty `why` is stored as empty, not `""`.
- **Repeats change nothing** (decisions 6 and 7): the same create returns the row as it is, even if the body differs; retiring a retired aspiration and bringing back an active one return it unchanged and write no audit row.
- **Errors** (decision 10): 404 for an id that doesn't exist or is someone else's; 409 for a reorder whose ids aren't exactly the active ones (one missing, one repeated, one retired or unknown), and for a create whose id is already another user's row; 422 for a body that doesn't validate.
- **Retire needs today's date in the phone's time zone** (decision 9), so this slice names the header: `X-Time-Zone`, an IANA name such as `America/Denver`. Only routes that need the day read it; there, a missing or unknown zone is 422.
- **Retire takes no body yet.** "Pause its work or keep it going" arrives with `goals-targets` and `recurring-items`.

Where the front end's hand-written types differ, the API follows `data-model.md` and #40 adapts: `position` (not `priority`), `retiredOn` as a day (not `retiredAt` as a moment), a reorder of all ids (not move up or down).

## Architecture decisions

- **Position is unique per owner by a constraint checked at the end of each statement** (`unique (user_id, position) deferrable initially immediate`). That settles open question 1: a reorder or a gap-closing update is one statement that renumbers several rows, which a plain unique index can refuse partway through. Not `initially deferred`: that checks only at commit, so a broken write would fail far from its cause, and the tests' rolled-back transactions would never check it at all.
- **A check constraint ties the columns together:** active means a position of 1 or more and no retired day; retired means no position and a retired day. "No gaps" can't be a constraint, so the rules module keeps it and tests check it after every route.
- **Deleted rows:** ADR-007 says unique rules ignore deleted rows through partial indexes, and a partial index can't be deferrable. The `delete` slice will empty a deleted aspiration's position (and loosen the check to allow it), which gets the same result. Noted in the migration.
- **Writes that change positions lock the owner's `users` row first** (`select ... for update`). Two creates arriving together, as an offline queue can send them, then take positions one after the other instead of one failing on the unique rule.
- **A folder per slice, as the pattern for later slices** (settled with Jan 2026-11-16). Shared modules stay at the top of `app/`.
  - `app/aspirations/routes.py`: the router. Thin.
  - `app/aspirations/models.py`: the request and response models.
  - `app/aspirations/rules.py`: create, reorder, retire and bring back, each several queries in one transaction. No FastAPI imports.
  - `app/errors.py`: `NotFound` and `NotAllowed`, raised by rules modules; `main.py` turns them into 404 and 409.
- **The database files stay organised by table, not by slice.** Migrations are one time-ordered folder, which dbmate needs. Queries are one file per table in `db/queries/`, generated into one module per table in `app/db/`, because later slices read and write earlier slices' tables.
- **Tests stay flat** (`tests/test_aspirations.py`) until one slice's tests get long.
  - `app/time_zone.py`: the `today` dependency reading `X-Time-Zone`, using the standard library's `zoneinfo`.
  - `app/openapi.py`: `uv run python -m app.openapi` writes `openapi.json` at the repo root.
- **Generated row models don't leave the API.** Each query returns the same columns, and one function maps a row to the hand-written `Aspiration`.
- **Tests go through a `client` fixture** that overrides `get_database` with the rolled-back `database` fixture. "Someone else's row" is tested with a second user inserted by the test.
- **No new dependency.**

## Dependency graph

```
1 the table and its constraints
      │
      ▼
2 list + create (router, models, client fixture, owner lock)
      │
      ├──▶ 3 reorder          ◄── checkpoint: sqlc and array parameters
      ├──▶ 4 edit (404)
      └──▶ 5 retire + bring back (time zone header)
                  │
                  ▼
            6 openapi.json and its test
                  │
                  ▼
            7 docs, spec marked built, note on front-end #40
```

Built in number order. Reorder comes third because it carries the one tool risk.

## Risks

| Risk | If it happens |
| --- | --- |
| sqlc or the Python plugin can't take a `uuid[]` parameter with `unnest ... with ordinality` | Reorder sets each position with one small query in a loop, with `set constraints ... deferred` for that transaction. Stays inside the slice; recorded for ADR-007. |
| `zoneinfo` finds no time zone data on some host | It works on macOS. A Linux container may need the `tzdata` package, which is a dependency question for hosting, not now. Noted in the README. |
| The locked `users` row makes writes queue | Intended, and one user's volume is tiny. |

## Checkpoints

- **After task 1:** migration goes up, down and up with `schema.sql` unchanged.
- **After task 3:** report whether the one-statement reorder generated cleanly or the fallback was used.
- **After task 6:** every spec criterion but the docs and the front end's is met; the four checks pass.

## Decision for Jan

The spec's criterion "the front end's types are regenerated from the new schema and its mock client compiles against them" can't be met inside this slice: the command that generates the types is the first thing front-end #40 builds, and it needs a new front-end dependency. Recommended: this slice delivers `openapi.json`, the criterion moves to #40, and the spec says so. Approving the plan approves that.
