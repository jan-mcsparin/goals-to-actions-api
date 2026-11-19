# Spec: Settings and sync

Status: draft 2026-11-13; finalised when its plan is written. Issue: [#13](https://github.com/jan-mcsparin/goals-to-actions-api/issues/13). Module `settings-sync` in the [map](README.md). Depends on `database-foundation`.

## Objective

Two small things that sit across the whole API: the person's one setting, and a check that the API behaves the way the phone's cache and offline queue need (ADR-004).

The write conventions themselves (device-made ids, creates and actions safe to repeat, the time zone header) are [shared decisions](README.md#shared-decisions) used from slice 2. This slice doesn't introduce them; it proves they held everywhere.

References: [`data-model.md`](../../docs/data-model.md#users), [ADR-004](../../docs/adr/0004-instant-open.md), [ADR-010](../../docs/adr/0010-week-document-and-replayed-queue.md), front-end issue #39, the front end's settings spec.

## Scope

**In:**

- `getSettings`, `setIntensity`. Intensity is stored on the user; nothing resets it or suggests changing it.
- The phone's time zone: the name sent with each request is stored on the user as last known, and a name that isn't a real zone is refused.
- A test, run over every route in the OpenAPI schema, that sending the same write twice gives the same answer and the same data.
- A test over every queueable write (ADR-010; shared decisions 13 to 15) that one aimed at a row that is deleted, set aside or in a week the task has left answers 404 or 409, never 500, and that a create aimed at a day no longer allowed lands in the bank.
- A written description in the README of what the front end can rely on: the list of queueable writes, that they are sent one at a time in order, what each answer means for the queue (success, 404 or 409 dropped, anything else retried), and that their request bodies only change by addition.

**Out (later):**

- A "what changed since" read. The phone refetches the week document instead (ADR-010).
- Version numbers or conflict responses. The last write to arrive wins.
- Push or live updates to a second device.
- Notifications, export, changing the week's start day.

## Testing strategy

As shared, plus the every-route repeat test above, and: a queued write against a deleted row answers in a way the front end can drop it (404, not 500); two devices changing one task, last write wins.

## Boundaries

As shared. **Never:** trust the phone's clock for ordering; store an offset.

## Success criteria

- [ ] Intensity reads and saves, and the week's read marks days against it. Changing it moves nothing (ADR-013).
- [ ] The user's time zone follows the phone.
- [ ] Every write in the API passes the repeat test.
- [ ] The README says what the offline queue can rely on.
- [ ] The front end's types are regenerated from the new schema and its mock client compiles against them.
- [ ] The four checks pass.

## Open questions

None left.

Settled 2026-11-19 (ADR-013): intensity stays in this slice. It no longer changes what the planner places, only which days the week's read marks as full, and every user reads as Normal until then.

Settled 2026-11-16 (ADR-010): no "what changed since" read; a resent create whose body differs from the stored row returns the row as it is, and the difference is ignored.
