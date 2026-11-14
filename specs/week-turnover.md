# Spec: Week turnover

Status: draft 2026-11-13; finalised when its plan is written. Module `week-turnover` in the [map](README.md). Depends on `tasks-week` and `recurring-items`.

## Objective

What happens when a week ends and the next begins: last week's unfinished tasks roll over or lapse, and the new week's bank fills with goal sessions, recurring tasks, rollovers and upcoming tasks now due. This is the first half of the planner (ADR-008); it decides what is in the week, not which day anything is on.

References: [`data-model.md`](../../docs/data-model.md#task_weeks) (how a week ends, the rules), [ADR-006](../../docs/adr/0006-task-weeks.md), [`product-rules.md`](../../docs/product-rules.md#planning), front-end issue #35.

## Scope

**In:**

- **Closing a week**, by origin: weekly-target tasks lapse; flexible recurring tasks lapse at the end of their period and carry inside it; fixed-day recurring tasks and tasks added by hand roll over into the next week's bank. Tasks set aside stay set aside.
- **Filling a week**:
  - one task per session of each active building goal's target for that week;
  - recurring tasks due in that week, by schedule kind;
  - open tasks whose due date falls in the week and have no row yet.
- **Safe to run twice.** Generated tasks are unique per goal or item, period and number, and `planned_through_week` on the user records how far filling has got. The week never goes backwards.
- **When it runs:** see the first open question.
- `getUpcoming`: open tasks with a later due date and no row yet.
- "Still matter?": the read marks a task that has rolled over twice and hasn't been answered since; `answerStillMatters` takes keep, schedule (onto a day) or drop.
- Changes mid-week that alter what the week should hold: a target raised or lowered, a goal created, an item added or its schedule changed.

**Out (later):**

- Placing anything on a day (`planner`).
- A job runner or scheduler, unless the first open question goes that way.

## Testing strategy

Most of this slice is set-based SQL with dates, so most tests are at that level, with the day passed in, never read from the clock:

- each row of "how a week ends" in the data model;
- filling twice creates nothing new;
- flexible periods: weekly, two weeks anchored on starts-on, monthly across a month boundary;
- a paused goal and a turned-off item get nothing;
- a week of 1 of 3 is followed by a week of 3, not 5;
- several weeks with no request in between;
- the phone's week behind the server's `planned_through_week`.

## Boundaries

As shared. **Always:** closing and filling a week is one transaction. **Never:** read the clock inside a rule; create a task a unique index would have to refuse as the normal path.

## Success criteria

- [ ] A new week's bank holds exactly what the rules say, and last week's rows are closed with the right outcome.
- [ ] Running turnover again changes nothing.
- [ ] The upcoming list and "Still matter?" read and answer correctly.
- [ ] The front end's types are regenerated from the new schema and its mock client compiles against them.
- [ ] The four checks pass.

## Open questions

1. **When does turnover run?** ADR-006 left it to the API. Options: on the first request of a new week, or a scheduled job. With one user, the first request is indistinguishable from a job and needs nothing extra to host, so I'd start there and keep the rule callable from a job later. It does mean "a plan exists even if you never open it" is true only in the sense that it exists the moment you look.
2. **Weeks nobody opened.** After three weeks away, are the two skipped weeks filled and closed one by one (history shows three lapsed weeks of sessions), or skipped (history shows nothing)? For quitting goals silence is unknown, not a slip; the same spirit suggests skipping.
3. **A target changed mid-week:** raising 3 to 4 adds a session; lowering 3 to 2 with all three still open removes which one?
4. **"Rolled over two weeks":** two rows with the outcome rolled over, counted since the last answer? Confirmed against issue #35.
