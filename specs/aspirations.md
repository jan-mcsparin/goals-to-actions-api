# Spec: Aspirations

Status: draft 2026-11-13; finalised when its plan is written. Issue: [#4](https://github.com/jan-mcsparin/goals-to-actions-api/issues/4). Module `aspirations` in the [map](README.md). Depends on `database-foundation`.

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

- [ ] The six routes work as described and appear in the OpenAPI schema in camelCase.
- [ ] The position rule holds after every route, and the database refuses two active aspirations in the same position.
- [ ] Every write appears in the audit log with its action.
- [ ] The front end's types are regenerated from the new schema and its mock client compiles against them.
- [ ] The four checks pass.

## Open questions

1. **How is position kept unique while a reorder is in progress?** A deferred constraint, or a rewrite in one statement. Settled in the plan once slice 1 shows what sqlc handles.
2. **Does `listAspirations` carry counts** (goals, "2 of 3 on track") that the Aspirations tab shows? If so they arrive with `goals-targets`, and this slice returns the aspiration alone.
