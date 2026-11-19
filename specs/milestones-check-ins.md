# Spec: Milestones and check-ins

Status: built 2026-11-17. Issue: [#6](https://github.com/jan-mcsparin/goals-to-actions-api/issues/6). Module `milestones-check-ins` in the [map](README.md). Depends on `goals-targets`.

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

- [x] Milestones can be added, edited, reordered and checked in, on building and quitting goals only.
- [x] Every check-in is kept, and the goal's read shows the count and the latest result.
- [x] The three follow-ups work and add no check-in: keep is its own route; move and adjust are edits.
- [x] Regenerating the front end's types stays with the front end's issue #40, as for the earlier slices.
- [x] The four checks pass.

## The contract, as built

| Operation | Route | Body |
| --- | --- | --- |
| `getGoal` | `GET /api/goals/{id}` | |
| `addMilestone` | `PUT /api/milestones/{id}` | `goalId`, `measurableLine`, `targetDate` (optional) |
| `updateMilestone` | `PATCH /api/milestones/{id}` | `measurableLine`, `targetDate`; sent whole |
| `reorderMilestones` | `POST /api/goals/{id}/milestones/reorder` | `ids`: every milestone of the goal, in order |
| `keepMilestone` | `POST /api/milestones/{id}/keep` | |
| `checkIn` | `PUT /api/check-ins/{id}` | `goalId`, `milestoneId` (`null` for the goal's own line), `outcome` (`hit` or `notYet`), `result` (optional) |

Each returns the goal's page, and needs `X-Time-Zone`: `goal` (as `goals-targets` returns it), `aspiration` (`id` and `name`, or `null`), `milestones` in order (`id`, `position`, `measurableLine`, `targetDate`, `status`: `upcoming`, `hit` or `notYet`, and `result`: its latest check-in's result, hit or not yet, `null` while it's upcoming or when that check-in had none), `progress` (`hit` and `of`; a reached goal counts complete, `hit` equal to `of`, since milestones never checked in were passed on the way), and `latest` (`result` and `checkedInOn`, or `null`). Goal writes keep returning the goal alone. `aspiration` and each milestone's `result` were added for the front end's #41 (issue #26).

## Settled

1. **A hit on the goal's own line marks the goal reached,** in the same transaction, as "I reached it" does (`flows.md`, flow 6). A not yet there is kept as a check-in and changes nothing else.
2. **Moving a date later pushes the later dated milestones out** by the same number of days, capped at the deadline. Undated ones stay undated; moving earlier, or giving an undated milestone a date, moves nothing else (`flows.md`, decided Nov 10).
3. **A goal's deadline can't move before a milestone's date:** `updateGoal` answers 409, and the person moves the milestone first.
4. **Move and adjust are `updateMilestone`.** Editing a "not yet" milestone makes it upcoming; editing a hit one keeps it hit. Keep is `keepMilestone`: from "not yet" it makes it upcoming, on an upcoming one it changes nothing, on a hit one it's a 409.
5. **Only Next can be checked in:** the first milestone that isn't hit, or the goal's own line once every milestone is hit. Anything else is a 409, as is a goal that is reached, ended or one-off. A paused goal can be checked in.
6. **Progress** is the milestones hit, plus one once the goal is reached, out of the milestones plus one.
7. **The check-in's day is the phone's today.** The same check-in sent twice is kept once.
8. **The database refuses what it can:** a milestone on a one-off or another owner's goal (a foreign key on the goal, its owner and its type), two milestones of a goal in one position (checked when each statement ends, so a reorder is one statement), a check-in naming another goal's milestone. "Between start and deadline" spans two tables, so `app/milestones/rules.py` keeps it.
9. **Input limits:** a milestone's line and a check-in's result are at most 500 characters.

## Left for later

- Deleting a milestone (`delete`) must free its position.
- No read of the full check-in history: nothing on screen shows more than "Latest".
