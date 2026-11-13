# Spec: Settings and sync

Status: draft 2026-11-13; finalised when its plan is written. Module `settings-sync` in the [map](README.md). Depends on `database-foundation`.

## Objective

Two small things that sit across the whole API: the person's one setting, and a check that the API behaves the way the phone's cache and offline queue need (ADR-004).

The write conventions themselves (device-made ids, creates and actions safe to repeat, the time zone header) are [shared decisions](README.md#shared-decisions) used from slice 2. This slice doesn't introduce them; it proves they held everywhere.

References: [`data-model.md`](../../docs/data-model.md#users), [ADR-004](../../docs/adr/0004-instant-open.md), front-end issue #39, the front end's settings spec.

## Scope

**In:**

- `getSettings`, `setIntensity`. Intensity is stored on the user; nothing resets it or suggests changing it.
- The phone's time zone: the name sent with each request is stored on the user as last known, and a name that isn't a real zone is refused.
- A test, run over every route in the OpenAPI schema, that sending the same write twice gives the same answer and the same data.
- A written description in the README of what the front end can rely on: which writes can be queued and resent, in what order, and what happens when a queued write no longer applies (checking off a task deleted on the laptop).

**Out (later):**

- A "what changed since" read. See the first open question.
- Push or live updates to a second device.
- Notifications, export, changing the week's start day.

## Testing strategy

As shared, plus the every-route repeat test above, and: a queued write against a deleted row answers in a way the front end can drop it (404, not 500); two devices changing one task, last write wins.

## Boundaries

As shared. **Never:** trust the phone's clock for ordering; store an offset.

## Success criteria

- [ ] Intensity reads and saves, and the planner's next draft uses it.
- [ ] The user's time zone follows the phone.
- [ ] Every write in the API passes the repeat test.
- [ ] The README says what the offline queue can rely on.
- [ ] The four checks pass.

## Open questions

1. **Does the phone need "what changed since I last asked"?** ADR-004 only needs Today to render from the cache and then refresh, which whole-screen reads already do. I'd not build a changes feed until a screen is slow without one.
2. **Should intensity move earlier?** It is one small route pair and the planner reads it. It could ride with `planner`, leaving this slice as the sync check alone.
3. **A resent create whose body differs from the stored row** (the phone edited it offline, then the create and the edit both arrive): the create returns the row as it is and the edit then applies. Is ignoring the difference right, or should it be a 409?
