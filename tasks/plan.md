# Implementation Plan: Settings and sync (#13)

Spec: [`../specs/settings-sync.md`](../specs/settings-sync.md). Tasks: [`todo.md`](todo.md). (The plan for #12 is in git history.)

## Overview

Two small routes for the one setting, the phone's time zone kept on the user, and two tests that run across the whole API to prove it behaves the way the phone's cache and offline queue need (ADR-004, ADR-010). The README then says what the queue can rely on.

Six tasks. **One PR** in the API, `settings-sync` (closes #13), and one small PR in the front end for the regenerated types. The front end's #39 wires Settings and the queue later.

## The contract

New. Neither is queueable (ADR-010).

| Operation | Route | Returns |
| --- | --- | --- |
| `getSettings` | `GET /api/settings` | `Settings` |
| `setIntensity` | `PUT /api/settings/intensity`, body `{"intensity": "goingHard"}` | `Settings` |

`Settings` is `{"intensity": "easingOff" \| "normal" \| "goingHard"}`. The time zone isn't in it: it's not a setting (`data-model.md`). Nor is a date set on: the data model dropped it, and the audit log has it. The front end's mock `Settings` still has `intensitySetOn`; that's for its #39.

## Architecture decisions

- **A new `app/settings/` slice** with `routes.py` and `models.py`. The queries `GetUser` and `SetIntensity` already exist. `setIntensity` is a `PUT` that states its end result, so sending it twice changes nothing more. It doesn't take the user lock and runs no planner: changing intensity moves nothing (ADR-013); the week read already marks days against it.
- **The time zone is kept by `Today`.** `today()` already reads the user; when the header's zone differs from the stored one, it saves it in its own small write (audit action "set time zone"). A request from the same zone writes nothing. Routes that don't need the day don't ask for the header, so don't save it; the zone is "last known", and every route that works out a day does. A name that isn't a zone is already refused (422) before anything is saved.
- **The repeat test is one table in `tests/test_repeats.py`:** for each write operation, how to arrange it and the request. It sends the request twice and checks the same status and body both times, and that a snapshot of the user's rows (every table, leaving out `updated_at`) is the same after the second as after the first. A last test reads the OpenAPI schema and fails if any `PUT`, `POST`, `PATCH` or `DELETE` operation has no row, so a new write can't skip it.
- **The stale-queue test is `tests/test_queued_writes.py`,** over the ten queueable writes (`addTask`, `checkOffTask`, `uncheckTask`, `placeTask`, `moveTaskToBank`, `swapTasks`, `answerQuitDay`, `clearQuitDay`, `rateUrge`, `clearUrgeRating`): aimed at a deleted row, a set-aside task, or a week the task has left, each answers 404 or 409. The test client re-raises server errors, so a 500 fails the test. A create aimed at a day no longer allowed lands in the bank. Two devices updating one task: the last to arrive wins.
- **No migration.** `users` already has `intensity` and `time_zone`.

## Dependency graph

```
getSettings, setIntensity (1)    time zone follows the phone (2)
        └──────────────┬───────────────┘
        repeat test: aspirations, goals, milestones, check-ins (3)
                       │
        repeat test: quitting, items, tasks, weeks, settings; every write covered (4)
                       │
        queued writes that no longer apply; last write wins (5)
                       │
        README, docs, the contract, the front end's types (6)
```

## Task list

- [x] Task 1: Read and set intensity
- [x] Task 2: The time zone follows the phone

Checkpoint after task 2: the new behaviour is in; the four checks pass.

- [x] Task 3: Repeat test, first half
- [x] Task 4: Repeat test, second half, and every write covered
- [x] Task 5: Queued writes that no longer apply

Checkpoint after task 5: every write is proved safe to repeat; the four checks pass.

- [ ] Task 6: What the queue can rely on; docs, the contract and the front end's types

Checkpoint after task 6: the slice is done, and the front end's mock compiles against the new types.

## Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| A repeat test finds a write that isn't safe to repeat | High | Stop and fix it in its own commit with its own test before carrying on; if the fix changes behaviour, ask. |
| Saving the time zone adds a write to every request | Med | Only when it changes; a test that a second request from the same zone writes no audit row. |
| The snapshot misses a change (a timestamp moved) | Med | Compare every column but `updated_at`; tests run in one transaction, so `now()` doesn't move between the two sends anyway. |
| The table falls behind new routes | Med | The coverage test reads `openapi.json`'s operations. |
