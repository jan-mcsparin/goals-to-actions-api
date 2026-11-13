# Spec: Quitting goals

Status: draft 2026-11-13; finalised when its plan is written. Module `quitting-goals` in the [map](README.md). Depends on `goals-targets`.

## Objective

The daily record of a quitting goal: a yes or no for the day, and now and then how strong the urge was. Silence is never counted against the person.

References: [`data-model.md`](../../docs/data-model.md#quit_days) (quit_days, urge_ratings), [`product-rules.md`](../../docs/product-rules.md#tone-and-prompts), front-end issue #37.

## Scope

**In:**

- The `quit_days` table (goal, day, held) and the `urge_ratings` table (goal, rated on, level: low, some, strong). One row per goal per day in each.
- Routes: `answerQuitDay` (yes or no for a day; answering again replaces it), `clearQuitDay` (back to unknown), `rateUrge`, `clearUrgeRating`.
- The goal's read gains the record: recent days as held, not held or unknown, the current run of held days, and recent urge levels. All worked out, none stored.
- The rules: only on quitting goals; no day before the goal's start date or after today.

**Out (later):**

- Any reminder to answer. The app never asks.
- Suggesting the goal is reached because the urge has stayed low. The read can carry the fact; only the person marks it reached.
- Quit days as tasks: they never enter the bank or count against the cap.

## Testing strategy

As shared, plus: a gap of days reads as unknown and doesn't break or reset anything it shouldn't; answering the same day twice leaves one row; a quit day on a building goal is refused by the database.

## Boundaries

As shared. **Never:** a response that words an unanswered day, or a "no", as failure; a stored streak.

## Success criteria

- [ ] A day can be answered, changed and cleared, and an urge rated and cleared.
- [ ] The goal's read shows the record with unknown days as unknown.
- [ ] The four checks pass.

## Open questions

1. **Does an unknown day end a run of held days,** pause it, or count as neither? "Silence isn't a slip" suggests the run continues across it, counting only answered days.
2. **Can a past day be answered?** Yesterday, surely; any day since the start?
3. **Where the daily answer sits on screen** is still open on front-end issue #37. It may add the quitting goals' state to the day's read.
