# Spec: Milestones and check-ins

Status: draft 2026-11-13; finalised when its plan is written. Issue: [#6](https://github.com/jan-mcsparin/goals-to-actions-api/issues/6). Module `milestones-check-ins` in the [map](README.md). Depends on `goals-targets`.

## Objective

The benchmarks on a building or quitting goal, and the record of each time the person checked in against one. This is what lets a goal's page say "2 of 6", "Started at" and "Latest", and what makes falling short a "not yet" with somewhere to go next.

References: [`data-model.md`](../../docs/data-model.md#milestones) (milestones, check_ins), [`product-rules.md`](../../docs/product-rules.md#tone-and-prompts), [`flows.md`](../../docs/flows.md).

## Scope

**In:**

- The `milestones` table: goal, position, measurable line, target date, status (upcoming, hit, not yet).
- The `check_ins` table: goal, milestone (empty for the goal's own line), outcome (hit, not yet), result, checked in on.
- Routes:
  - `addMilestone`, `updateMilestone`, `reorderMilestones`.
  - `checkIn`: against a milestone or the goal's own line, with an outcome and an optional result. It adds a check-in and sets the milestone's status.
  - The follow-up to a "not yet": keep (back to upcoming), move (a new date) or adjust (a new line). Each puts the milestone back to upcoming without a new check-in.
- `getGoal` gains the milestones in order, the progress count (milestones plus one for the goal itself), and the latest check-in with a result.
- The rules: milestones only on building and quitting goals; a target date between the goal's start and its deadline; positions 1 to n.

**Out (later):**

- Delete a milestone (`delete`).
- Metrics: numbers read from results (designed, not built).
- Any prompt to check in. The app never asks.

## Testing strategy

As shared, plus: a check-in history of several rows for one milestone; "latest" skips check-ins with no result; a milestone on a one-off goal is refused by the database; each follow-up leaves the check-in history untouched.

## Boundaries

As shared. **Never:** store "passed on the way" or the goal as a milestone row; wording in any response that reads as failure.

## Success criteria

- [ ] Milestones can be added, edited, reordered and checked in, on building and quitting goals only.
- [ ] Every check-in is kept, and the goal's read shows the count and the latest result.
- [ ] The three follow-ups work and add no check-in.
- [ ] The front end's types are regenerated from the new schema and its mock client compiles against them.
- [ ] The four checks pass.

## Open questions

1. **Does a "hit" on the goal's own line mark the goal reached,** or are those two steps? The rules say only the person marks a goal reached, which suggests the check-in offers it and `markGoalReached` does it.
2. **Moving a milestone's date: do later milestones' dates move with it?** The first model had rules about dates pushing each other. Confirmed from `flows.md` in the plan.
3. **Changing a goal's deadline to before a milestone's date:** refuse, or pull the milestone's date in?
