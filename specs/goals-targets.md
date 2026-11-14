# Spec: Goals and weekly targets

Status: draft 2026-11-13; finalised when its plan is written. Module `goals-targets` in the [map](README.md). Depends on `aspirations`.

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
  - `setWeeklyTarget`: takes effect this week.
  - `pauseGoal`, `resumeGoal`, `endGoal`, `markGoalReached`, `reopenGoal`, `goAgain`. Go again is the same goal made active again.
- Retiring an aspiration with its goals' work paused: `retireAspiration` gains that choice and pauses the aspiration's active goals in the same transaction.
- The rules: a deadline is never before the start date; weekly targets only on building goals; ended on is set by reached and ended, cleared by reopen and go again.
- "This one slipped" needs nothing stored: the read says whether an active goal's deadline has passed.

**Out (later):**

- Milestones and check-ins, and the "1 of 6" count (`milestones-check-ins`).
- Progress this week against the target, which needs tasks (`tasks-week`).
- Setting a paused goal's tasks aside, and returning them on resume (`tasks-week`).
- A one-off goal's steps: they are tasks (`tasks-week`).
- Daily answers on a quitting goal (`quitting-goals`).
- Keeping a reached goal's practice as a recurring item (`recurring-items`).
- Delete (`delete`). Metrics (designed, not built).

## Testing strategy

As shared, plus one test per status change, allowed and refused (a 409 for resuming a goal that isn't paused); a target change twice in one week leaves one row; last week's target is still readable after a change; a weekly target on a quitting goal is refused by the database.

## Boundaries

As shared. **Never:** infer a goal's type; add a "missed" status or a hard-deadline flag.

## Success criteria

- [ ] All three goal types can be created, read, edited and taken through every status change the flows allow.
- [ ] Weekly target history is kept per week.
- [ ] Retiring an aspiration can pause its goals.
- [ ] The rules above are refused by the database or the route, each with a test.
- [ ] The front end's types are regenerated from the new schema and its mock client compiles against them.
- [ ] The four checks pass.

## Open questions

1. **Which status changes are allowed from which?** The table (for example, can a paused goal be marked reached?) is written out from `flows.md` in the plan and confirmed then.
2. **Does bringing an aspiration back resume the goals its retiring paused?** Nothing stored says which goals were paused that way; only the audit log knows, and nothing may read it. So either all its paused goals resume, or none do and the person resumes them. I'd say none.
3. **A target change takes effect this week.** Should a change made on a Sunday wait for Monday instead? The data model says this week.
