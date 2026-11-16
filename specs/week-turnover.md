# Spec: Week turnover

Status: draft 2026-11-13, when-it-runs settled 2026-11-16; finalised when its plan is written. Issue: [#9](https://github.com/jan-mcsparin/goals-to-actions-api/issues/9). Module `week-turnover` in the [map](README.md). Depends on `tasks-week` and `recurring-items`.

## Objective

What happens when a week ends and the next begins: last week's unfinished tasks roll over or lapse, and the new week's bank fills with goal sessions, recurring tasks, rollovers and upcoming tasks now due. This is the first half of the planner (ADR-008); it decides what is in the week, not which day anything is on.

The two halves happen at different times (ADR-009). A week **opens** at 6 p.m. on the Sunday before it and **closes** when its own Sunday ends, or earlier if the person wraps it up. So from Sunday evening until the close, two weeks are open.

References: [`data-model.md`](../../docs/data-model.md#task_weeks) (how a week ends, the rules), [ADR-006](../../docs/adr/0006-task-weeks.md), [ADR-009](../../docs/adr/0009-week-opens-sunday-drafted-once.md), [`product-rules.md`](../../docs/product-rules.md#planning), front-end issue #35.

## Scope

**In:**

- **Closing a week**, by origin: weekly-target tasks lapse; flexible recurring tasks lapse at the end of their period and carry inside it; fixed-day recurring tasks and tasks added by hand roll over into the next week's bank. Tasks set aside stay set aside.
- **Opening a week**, which fills its bank and then calls the planner's first draft in the same transaction:
  - one task per session of each active building goal's target for that week;
  - recurring tasks due in that week, by schedule kind;
  - open tasks whose due date falls in the week and have no row yet.
- **Carry-overs arrive at the close,** not at the opening: a task can have only one row in play, so it can't be in next week while this week still holds it. They are handed to the planner as new arrivals.
- **When each runs** (ADR-009), with no job:
  - opening: the first request at or after 6 p.m. on Sunday, by the phone's time zone. The hour is one constant;
  - closing: the first request on Monday or later;
  - if nobody opened the app on Sunday evening, both happen on the first request of the new week, closing first, so the carry-overs are part of the first draft.
- **`wrapUpWeek`:** the same close, done by the person. Allowed once next week is open, refused before (409). Next week becomes the current one. Sending it twice changes nothing more. There is no undo.
- **What closing will do,** on the week's read: each unfinished task says whether it will carry over or end with the week, so the wrap-up sheet shows it without the front end knowing the rules.
- **Two markers on the user:** `planned_through_week` (the latest week opened; already on `users`) and `closed_through_week` (the latest week closed; a column this slice adds). The current week is the one after `closed_through_week` or the phone's week, whichever is later. The week never goes backwards.
- **Safe to run twice.** Generated tasks are unique per goal or item, period and number, and the two markers record how far opening and closing have got.
- **A week nobody opened is skipped.** A week with no rows is never filled or closed after the fact. Coming back after three weeks closes the weeks that have rows, in order, and opens the current one; a hand-added task carries straight into it as one carry-over.
- `getUpcoming`: open tasks with a later due date and no row yet.
- "Still matter?": the read marks a task that has rolled over twice and hasn't been answered since; `answerStillMatters` takes keep, schedule (onto a day) or drop.
- Changes mid-week that alter what the week should hold: a target raised or lowered, a goal created, an item added or its schedule changed.

**Out (later):**

- Placing anything on a day (`planner`).
- A job runner or scheduler. The opening and closing rules take the day and time as inputs, so a job can call them once the API is hosted.
- A way to undo a wrap-up.

## Testing strategy

Most of this slice is set-based SQL with dates, so most tests are at that level, with the day passed in, never read from the clock:

- each row of "how a week ends" in the data model;
- filling twice creates nothing new;
- flexible periods: weekly, two weeks anchored on starts-on, monthly across a month boundary;
- a paused goal and a turned-off item get nothing;
- a week of 1 of 3 is followed by a week of 3, not 5;
- several weeks with no request in between: nothing is created for them, and a hand-added task carries over once;
- a request at 5:59 p.m. on Sunday opens nothing, and one at 6 p.m. opens next week and leaves Sunday as it was;
- opened on Sunday evening, then closed on Monday: the carry-overs arrive then;
- never opened on Sunday evening: one request on Monday closes, opens and drafts;
- wrapping up on Sunday evening, twice, and before next week is open;
- the phone's week behind the current week after a wrap-up or a flight west.

## Boundaries

As shared. **Always:** closing a week is one transaction, and so is opening one with its first draft. **Ask first:** a job or scheduler. **Never:** read the clock inside a rule; create a task a unique index would have to refuse as the normal path.

## Success criteria

- [ ] A week opens on Sunday evening with exactly what the rules say, and Sunday's plan is untouched.
- [ ] A week closes on Monday, or when wrapped up, with each row given the right outcome and the carry-overs in the new week.
- [ ] Opening or closing again changes nothing.
- [ ] A week nobody opened leaves no rows.
- [ ] The upcoming list and "Still matter?" read and answer correctly.
- [ ] The front end's types are regenerated from the new schema and its mock client compiles against them.
- [ ] The four checks pass.

## Open questions

1. **A target changed mid-week:** raising 3 to 4 adds a session; lowering 3 to 2 with all three still open removes which one? With next week already open, the change applies there too.
2. **"Rolled over two weeks":** two rows with the outcome rolled over, counted since the last answer? Confirmed against front-end issue #35. A skipped week adds no row, so time away doesn't count towards it.
3. **A goal reached, ended or paused between the opening and the close:** its tasks in next week are set aside or dropped with the rest. Listed so the plan covers it.

Settled 2026-11-16 (ADR-009): when turnover runs, and what happens to weeks nobody opened.
