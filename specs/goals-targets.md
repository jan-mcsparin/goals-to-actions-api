# Spec: Goals and weekly targets

Status: built 2026-11-16. Issue: [#5](https://github.com/jan-mcsparin/goals-to-actions-api/issues/5). Module `goals-targets` in the [map](README.md). Depends on `aspirations`.

## Objective

Goals of all three types, their life (active, paused, reached, ended, and back), and a building goal's weekly target with its history. After this slice the Aspirations tab, an aspiration's page and most of a goal's page have real data.

References: [`data-model.md`](../../docs/data-model.md#goals) (goals, weekly_targets), [`product-rules.md`](../../docs/product-rules.md#the-model), [`flows.md`](../../docs/flows.md).

## Scope

**In:**

- The `goals` table: aspiration (optional), type, label, measurable line, baseline, status, start date, deadline, ended on.
- The `weekly_targets` table: kind (count, amount), sessions, amount, unit, effective-from week. One row per goal per week; a second change in the same week replaces the first.
- Routes:
  - `listGoals` (by aspiration, and those with none), `getGoal`.
  - `createGoal`: the type is given, never inferred; a building goal is created with its first target.
  - `updateGoal`: label, line, baseline, aspiration, deadline. Pushing a slipped deadline back is this route.
  - `setWeeklyTarget`: takes effect this week, or from next week once next week is open (ADR-009).
  - `pauseGoal`, `resumeGoal`, `endGoal`, `markGoalReached`, `reopenGoal`, `goAgain`. Go again is the same goal made active again.
- Retiring an aspiration with its goals' work paused: `retireAspiration` gains that choice and pauses the aspiration's active goals in the same transaction.
- The rules: a deadline is never before the start date; weekly targets only on building goals; ended on is set by reached and ended, cleared by reopen and go again.
- "This one slipped" needs nothing stored: the read says whether an active goal's deadline has passed.

**Out (later):**

- Milestones and check-ins, and the "1 of 6" count (`milestones-check-ins`).
- Progress this week against the target, which needs tasks (`tasks-week`).
- Setting a goal's tasks aside when it is paused, ended or reached, and returning them on resume, reopen and go again (`tasks-week`).
- A one-off goal's steps: they are tasks (`tasks-week`).
- Daily answers on a quitting goal (`quitting-goals`).
- Keeping a reached goal's practice as a recurring item (`recurring-items`).
- Delete (`delete`). Metrics (designed, not built).

## Testing strategy

As shared, plus one test per status change, allowed and refused (a 409 for resuming a goal that isn't paused); a target change twice in one week leaves one row; last week's target is still readable after a change; a weekly target on a quitting goal is refused by the database.

## Boundaries

As shared. **Never:** infer a goal's type; add a "missed" status or a hard-deadline flag.

## Success criteria

- [x] All three goal types can be created, read, edited and taken through every status change the flows allow.
- [x] Weekly target history is kept per week.
- [x] Retiring an aspiration can pause its goals.
- [x] The rules above are refused by the database or the route, each with a test.
- [x] Regenerating the front end's types moved to the front end's issue #40, as with aspirations: the command that does it is the first thing #40 builds.
- [x] The four checks pass.

## The contract, as built

| Operation | Route | Body |
| --- | --- | --- |
| `listGoals` | `GET /api/goals` | |
| `getGoal` | `GET /api/goals/{id}` | |
| `createGoal` | `PUT /api/goals/{id}` | `type`, `label`, `measurableLine`, `baseline`, `aspirationId`, `startDate` (today when left out), `deadline`, `weeklyTarget` (building goals only, and required there) |
| `updateGoal` | `PATCH /api/goals/{id}` | `label`, `measurableLine`, `baseline`, `aspirationId`, `deadline`; sent whole every time |
| `setWeeklyTarget` | `PUT /api/goals/{id}/weekly-target` | `kind` (`count` or `amount`), `sessions`, `amount` (amount targets only), `unit` |
| `pauseGoal`, `resumeGoal`, `endGoal`, `markGoalReached`, `reopenGoal`, `goAgain` | `POST /api/goals/{id}/pause`, `/resume`, `/end`, `/mark-reached`, `/reopen`, `/go-again` | |
| `retireAspiration` | `POST /api/aspirations/{id}/retire` | gains `itsWork`: `pause` or `keep`, required |

Every goal route needs the `X-Time-Zone` header and returns the goal: `id`, `aspirationId`, `type` (`building`, `quitting`, `oneOff`), `label`, `measurableLine`, `baseline`, `status`, `startDate`, `deadline`, `endedOn`, `slipped`, `weeklyTarget`, `createdAt`. `weeklyTarget` is the latest row (`kind`, `sessions`, `amount`, `unit`, `effectiveFrom`), so a change waiting for next week shows with an `effectiveFrom` after this week; it is `null` for quitting and one-off goals. The list is `{ "goals": [...] }`: under active aspirations by priority, then under retired ones, then those with none; within each, oldest first.

## Settled

1. **Status changes:**

   | Route | Allowed from | Sent again | Otherwise |
   | --- | --- | --- | --- |
   | pause | active | returns it unchanged | 409 |
   | resume | paused | returns it unchanged | 409 |
   | end, mark reached | active, paused | returns it unchanged | 409 |
   | reopen | reached | returns it unchanged | 409 |
   | go again | ended | returns it unchanged | 409 |

   End and mark reached set `endedOn` to today; coming back clears it. Resume, reopen and go again work under a retired aspiration.
2. **Bringing an aspiration back resumes none of its goals,** as `flows.md` already said.
3. **The database refuses what it can:** a goal under another owner's aspiration, and a target on a goal that isn't building or isn't the owner's, by foreign keys on two and three columns; a deadline before the start, `endedOn` out of step with the status, a target week that isn't a Monday, one target row per goal per week, sessions from 1 to 14, and an amount only on an amount target.
4. **A goal goes under an active aspiration** (409 otherwise), and can stay under one that has since retired.
5. **A deadline before the start date** is a 422 when both are in the body, and a 409 when the start date is stored or defaulted to today.
6. **The week a target change takes effect** is `app/weeks.py`'s `target_week`: the phone's week, or next week once `planned_through_week` is later. The same target again writes nothing.
7. **Every goal write takes the user lock,** and `tests/test_aspirations_lock.py` checks each one.
8. **Input limits:** a label is at most 200 characters, a measurable line and a baseline 500, a unit 100; an amount is above 0 and at most 1,000,000.

## Left for later

- Setting a goal's tasks aside on pause, end and reached, and returning them on resume, reopen and go again (`tasks-week`).
- "The current week" after a wrap-up, when `week-turnover` adds `closed_through_week` to `target_week`.
- Pausing an aspiration's recurring items on retire (`recurring-items`).
- `listAspirations` still returns aspirations alone. The Aspirations tab and an aspiration's page can draw their goals from `listGoals`; whether either needs a combined read is settled when the front end wires them.
