# Spec: Aspirations

Status: built 2026-11-16. Issue: [#4](https://github.com/jan-mcsparin/goals-to-actions-api/issues/4). Module `aspirations` in the [map](README.md). Depends on `database-foundation`.

## Objective

The first real feature, and the first route through the whole stack: a person's aspirations, in priority order, with retire and bring back. It also sets the pattern every later slice copies (router, models, queries, tests), so it is worth getting plain.

References: [`data-model.md`](../../docs/data-model.md#aspirations), [`product-rules.md`](../../docs/product-rules.md#the-model), [`flows.md`](../../docs/flows.md).

## Scope

**In:**

- The `aspirations` table: name, why, status (active, retired), position, retired on.
- Routes (names are what the front end will call):
  - `listAspirations`: active ones in priority order, then retired ones.
  - `createAspiration`: goes last among the active.
  - `updateAspiration`: name and why.
  - `reorderAspirations`: the active ids in their new order.
  - `retireAspiration`, `bringBackAspiration`: brought back, it goes last.
- `openapi.json`: the schema written to a committed file by one command, with a test that fails when it is out of date. The front end generates its types from it (its issue #40), and its diff shows every contract change in review.
- The rule that active aspirations are numbered 1 to n with no gaps and a retired one has no position, kept by the database where it can be and by the route where it can't.

**Out (later):**

- What retiring does to the aspiration's goals and recurring items (`goals-targets`, `recurring-items`). Here retiring changes only the aspiration.
- An aspiration's page with its goals (`goals-targets` adds goals to the read).
- Delete (`delete`).
- Keep life running. It isn't an aspiration and has no row; its page is read from tasks and recurring items with no goal and no aspiration.

## Testing strategy

As in the [shared conventions](README.md#shared-conventions), plus: positions stay 1 to n after create, reorder, retire and bring back; a reorder that leaves out or repeats an id is refused; retiring twice changes nothing.

## Boundaries

As shared. **Ask first:** any field not in the data model.

## Success criteria

- [x] The six routes work as described and appear in the OpenAPI schema in camelCase.
- [x] The position rule holds after every route, and the database refuses two active aspirations in the same position.
- [x] Every write appears in the audit log with its action.
- [x] `openapi.json` is committed, with a test that fails when it's out of date. Regenerating the front end's types from it moved to the front end's issue #40, which builds the command that does it.
- [x] The four checks pass.

## The contract, as built

| Operation | Route | Body |
| --- | --- | --- |
| `listAspirations` | `GET /aspirations` | |
| `createAspiration` | `PUT /aspirations/{id}` | `name`, `why` (optional) |
| `updateAspiration` | `PATCH /aspirations/{id}` | `name`, `why`; both sent every time |
| `reorderAspirations` | `POST /aspirations/reorder` | `ids`: every active id, in the new order |
| `retireAspiration` | `POST /aspirations/{id}/retire` | `itsWork` (`pause` or `keep`), added by `goals-targets`; needs the `X-Time-Zone` header |
| `bringBackAspiration` | `POST /aspirations/{id}/bring-back` | |

An aspiration is `id`, `name`, `why`, `status`, `position`, `retiredOn`, `createdAt`. The list is `{ "aspirations": [...] }`: active by position, then retired with the newest first.

## Settled

1. **Position is unique per owner by a deferrable constraint, checked when each statement ends,** and a reorder is one statement that renumbers from the ids sent. sqlc handles the `uuid[]` parameter. Not checked at commit: the tests' rolled-back transactions would never check it. "No gaps" is kept by `app/aspirations/rules.py`.
2. **`listAspirations` returns aspirations alone.** Goal counts join it in `goals-targets`; the list is wrapped in an object so they can.
3. **A reorder that isn't exactly the active ids is 409,** as is a create whose id is already another user's row.
4. **Writes that renumber lock the owner's `users` row first.** `tests/test_aspirations_lock.py` checks each one waits for it, on two real connections.
5. **Input limits:** a name is at most 200 characters and a why 2,000; a reorder lists at most 500 ids. Text with a NUL character is refused (422), since Postgres can't store it.

## Left for later

- Retire's "pause its work" pauses its goals since `goals-targets`; its recurring items join with `recurring-items`.
- Deleting an aspiration (`delete`) must empty its position and loosen the `aspirations_status_agrees` check to allow it.
