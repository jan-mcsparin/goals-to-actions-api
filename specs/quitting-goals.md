# Spec: Quitting goals

Status: built 2026-11-19, after the open question on runs was answered. Issue: [#11](https://github.com/jan-mcsparin/goals-to-actions-api/issues/11). Module `quitting-goals` in the [map](README.md). Depends on `goals-targets`.

## Objective

The daily record of a quitting goal: a yes or no for the day, and now and then how strong the urge was. Silence is never counted against the person.

References: [`data-model.md`](../../docs/data-model.md#quit_days) (quit_days, urge_ratings), [`product-rules.md`](../../docs/product-rules.md#tone-and-prompts), front-end issue #37.

## Scope

**In:**

- The `quit_days` table (goal, day, held) and the `urge_ratings` table (goal, rated on, level: low, some, strong). One row per goal per day in each.
- Routes: `answerQuitDay` (yes or no for a day; answering again replaces it), `clearQuitDay` (back to unknown), `rateUrge`, `clearUrgeRating`. All four are queueable writes (ADR-010): each names its day and states its end result.
- The week read (`tasks-week`) gains each active quitting goal's answers and urge ratings for that week's days, so the phone can show and answer them offline.
- The goal's read gains the record: recent days as held, not held or unknown, the current run of held days, and recent urge levels. All worked out, none stored.
- The rules: only on quitting goals; any day from the goal's start date to today, so an answer given offline still lands when it is sent days later.

**Out (later):**

- Any reminder to answer. The app never asks.
- Suggesting the goal is reached because the urge has stayed low. The read can carry the fact; only the person marks it reached.
- Quit days as tasks: they never enter the bank or count against the cap.

## Testing strategy

As shared, plus: a gap of days reads as unknown and doesn't break or reset anything it shouldn't; answering the same day twice leaves one row; a quit day on a building goal is refused by the database.

## Boundaries

As shared. **Never:** a response that words an unanswered day, or a "no", as failure; a stored streak.

## Success criteria

- [x] A day can be answered, changed and cleared, and an urge rated and cleared.
- [x] The goal's read shows the record with unknown days as unknown.
- [x] The front end's types are regenerated from the new schema and its mock client compiles against them.
- [x] The four checks pass.

## Open questions

1. ~~**Does an unknown day end a run of held days,** pause it, or count as neither?~~ Neither (Jan, 2026-11-19): the run counts held answers since the last no, and the read also counts the unanswered days inside it (below).
2. **Where the daily answer sits on screen** is still open on front-end issue #37.

Settled 2026-11-16 (ADR-010): any day from the goal's start to today can be answered, and the week read carries the quitting goals' state.

## What changed while building

Settled with Jan when the plan was written (`../tasks/plan.md`, 2026-11-19):

- **The routes:** `answerQuitDay` is `PUT /goals/{goalId}/quit-days/{day}` with `{ "held" }`, `rateUrge` is `PUT /goals/{goalId}/urges/{day}` with `{ "level" }`, and each is cleared by `POST .../clear`. All four return the whole day, `QuitDay { goalId, day, held, urge }`, with `null` for unknown.
- **A run counts held answers since the last no,** or since the start. An unknown day neither ends it nor adds to it.
- **`unknownInRun`:** the goal's read counts the days before today inside the run that have no answer. It gently invites filling them in, and the front end can show the run as unknown until they are. Today isn't counted while it's still going.
- **The goal's page shows the last 28 days,** newest first; the run reads every answer since the start.
- **A day can be answered whatever the goal's status,** so an answer queued before another device paused or ended the goal still lands; but not a day after the goal ended or was reached. An ended or reached goal's record stops on that day, so the days after it are never counted as unknown (review, 2026-11-19). A paused goal's days still count: pauses aren't stored as dates.
- **The server makes each row's id,** since a day is named by its goal and date (shared decision 6 notes the exception). **Clearing sets `deleted_at`**; a unique index over live rows keeps one per goal per day, and answering is an upsert on it. The same answer again writes nothing, not even an audit row.
- **No "the urge has stayed low" fact yet.** Nothing asked for it; the front end's #37 can.
