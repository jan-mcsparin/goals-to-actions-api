# Implementation Plan: Quitting goals (#11)

Spec: [`../specs/quitting-goals.md`](../specs/quitting-goals.md). Tasks: [`todo.md`](todo.md). (The plan for #10 is in git history.)

## Overview

A quitting goal's daily record: a yes or no for a day, and sometimes how strong the urge was. Both tables are new. Four writes answer and clear them; the goal's page and the week read carry the record. A day with no answer is unknown, never a slip, and nothing asks about it.

Six tasks. **One PR** in the API, `quitting-goals` (closes #11), and one small PR in the front end for the regenerated types. The front end's #37 builds the screens later.

## The contract

New, all queueable (ADR-010): each names its goal and day and states its end result, so sending it twice changes nothing more.

| Operation | Route | Body | Returns |
| --- | --- | --- | --- |
| `answerQuitDay` | `PUT /api/goals/{goalId}/quit-days/{day}` | `{ "held": true }` | `QuitDay` |
| `clearQuitDay` | `POST /api/goals/{goalId}/quit-days/{day}/clear` | | `QuitDay` |
| `rateUrge` | `PUT /api/goals/{goalId}/urges/{day}` | `{ "level": "low" }` (`low`, `some`, `strong`) | `QuitDay` |
| `clearUrgeRating` | `POST /api/goals/{goalId}/urges/{day}/clear` | | `QuitDay` |

`QuitDay` is one day of the record: `{ "goalId", "day", "held": true | false | null, "urge": "low" | "some" | "strong" | null }`. `null` is unknown. Every write returns the whole day, so the phone has both halves after either.

Refused: 404 for a goal that doesn't exist or isn't yours; 409 for a goal that isn't quitting, a day before the goal's start, or a day after today (shared decisions 10 and 15).

Changed:

- **`GoalPage` gains `quitRecord`**, empty except on a quitting goal: `{ "days": [QuitDay, ...], "heldRun": 12, "unknownInRun": 2 }`. `days` is the last 28 days up to today, from the goal's start at the earliest, newest first. `heldRun` counts held answers since the last "no"; `unknownInRun` counts the days before today since then that have no answer, so the front end can show the run as unknown until they're filled in. Both are worked out from every answer on each read, never stored.
- **`Week` gains `quittingGoals`**: each active quitting goal that has started by the week's end, `{ "id", "label", "days": [QuitDay, ...] }`, one per day of the week from its start. The phone can show and answer them offline.

## Architecture decisions

- **Two tables, as in the data model:** `quit_days (goal_id, day, held)` and `urge_ratings (goal_id, rated_on, level)`, with the shared columns and triggers. A `goal_type` column fixed to `'quitting'` with a foreign key to `goals (id, user_id, type)`, the way `weekly_targets` does it, so the database refuses a row on any other goal or another owner's.
- **One row per goal per day,** kept by a unique index over rows that aren't deleted. Answering is an upsert on it, so a repeat or a change leaves one row, and two devices answering together leave the last answer (shared decision 8).
- **The server makes the row's id.** A day is named by its goal and date, so the phone has no id to send. This is the one table where the device doesn't make it.
- **Clearing sets `deleted_at`.** No row means unknown; the audit log keeps what was there. Answering again afterwards adds a new row.
- **New slice folder `app/quitting/`** (routes, models, rules, and `record.py` for the record both reads use). The goal's page and the week read call `record.py`.
- **No user lock.** Each write touches one row through one statement; the upsert is what keeps it to one row.

## Dependency graph

```
quit_days + urge_ratings tables (1)
    ├── answerQuitDay, clearQuitDay (2)
    │      └── rateUrge, clearUrgeRating (3)
    ├── the goal's record on its page (4)
    └── the week's quitting goals (5)
          └── docs, openapi.json, the front end's types (6)
```

## Task list

- [x] Task 1: The quit_days and urge_ratings tables
- [x] Task 2: Answer and clear a day
- [x] Task 3: Rate and clear the urge

Checkpoint after task 3: the four writes work; the four checks pass.

- [x] Task 4: The record on the goal's page
- [x] Task 5: Quitting goals on the week read
- [x] Task 6: Docs, the contract and the front end's types

Checkpoint after task 6: the slice is done, and the front end's mock compiles against the new types.

## Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| A queued answer sent days later is refused because "today" moved | Med | Any day from the start to today is allowed; only future days and days before the start are refused. A test answers a day a week old. |
| A response or field words a "no" or a gap as failure | Med | Fields are `held: true/false/null`, no "slipped" or "missed"; the run counts held answers and a gap never breaks it. |
| The unique index and soft clears fight (clear, answer, clear) | Low | A test runs that cycle and checks one live row at each step. |

## Assumed, for review with this plan

1. **A run counts held answers since the last "no"** (open question 1; Jan, 2026-11-19: unknown days don't break the run). An unknown day neither ends the run nor adds to it. A "no" starts it again from zero. Any past day from the start can be answered later.
   - **The read also counts the unanswered days inside the run** (`unknownInRun`; Jan, 2026-11-19: it gently invites filling them in). Today isn't counted while it's still going.
2. **The goal's page shows the last 28 days** (four weeks), newest first. Older days stay stored.
3. **A day can be answered whatever the goal's status.** A queued answer made before another device paused or ended the goal still lands, and the record is history either way.
4. **The routes above**, with `PUT` for an answer and `POST .../clear` to clear it, as every other action here does.
5. **Clearing is a soft delete,** and the server makes each row's id (above).
6. **No "urge has stayed low" fact yet.** The spec allows it, but nothing asks for it; the front end's #37 can ask.
