# Implementation Plan: The planner (#10)

Spec: [`../specs/planner.md`](../specs/planner.md). Tasks: [`todo.md`](todo.md). (The plan for #9 is in git history.)

## Overview

Fill the hook `week-turnover` left (`place_new_work` in `app/planner.py`). When a week opens, its recurring work goes on days: fixed-day tasks on their day, a goal's sessions and a flexible item's tasks spread evenly. New recurring work that arrives mid-week goes on days after today. Everything else stays in the bank. The week read gains the full-day mark. Nothing else moves, ever.

Six tasks. **One PR** in the API, `planner` (closes #10), and one small PR in the front end for the regenerated types.

## The contract

No new routes. Changed:

- **`Week` gains `days`**: the seven days, Monday first, each `{ "day": "2026-11-16", "cap": 4, "full": false }`. `cap` comes from intensity (Easing off 3, Normal 4, Going hard 6). Worked out on every read; nothing is stored.
- **What comes back on days changes:** after a week opens, its recurring tasks have a `plannedDay` instead of sitting in the bank. `placedByHand` stays `false` on them.

Every request body is unchanged (shared decision 14).

## Architecture decisions

- **The placing rule is one pure function**, `place(week, first_day, load, new_work) -> list[Placement]`, in `app/planner.py`. `load` is how many tasks each day already holds; each item of `new_work` carries its task id, its group (the goal or item), its place in the order, its fixed day if it has one, and whether its group already has tasks this week. No database, no clock. It is deterministic: ties break by day, then by task id.
- **`place_new_work` keeps its signature.** It reads what the function needs with one new query, calls it, and writes each placement. The three callers in `app/turnover/rules.py` don't change.
- **The database refuses the two forbidden writes** in the planner's one write query, `PlaceGeneratedTask`: it only updates a row that is in the bank, not placed by hand, with no outcome, in the day's week, and only when the day is on or after the first day allowed (`where ... and placed_by_hand = false and planned_day is null and outcome is null and @day >= @first_day`). A write it refuses changes nothing, and a test proves it. No trigger: the database can't know the phone's today, so the query is the narrowest place it can refuse.
- **A goal or item isn't placed before it starts.** The first day it may use is the later of the planner's first day and its own start date. (`goal_slots` and `item_slots` already count days that way, so the sessions they make fit.)
- **The order** (spec, "The order") is a sort key built in the query: fixed-day first; then flexible items with no aspiration; then by the aspiration's position, goals by `created_at` before items; then goals and items with no aspiration or a retired one, by `created_at`.
- **The full-day mark** counts every task on the day that is open or done (not dropped, not set aside), the same rows the week read returns with a `plannedDay`.

## Dependency graph

```
place(): the pure rule (1)
    └── place_new_work: read, place, guarded write; when a week opens (2)
          ├── new recurring work mid-week: goals, targets, items (3)
          │      └── a new fixed-day item due today goes on today (4)
          └── the full-day mark on the week read (5)
                └── docs, openapi.json, the front end's types (6)
```

## Task list

- [x] Task 1: The placing rule
- [x] Task 2: Place when a week opens
- [x] Task 3: Place new recurring work on later days

Checkpoint after task 3: recurring work lands on days; the four checks pass.

- [x] Task 4: A new fixed-day item due today goes on today
- [x] Task 5: The full-day mark
- [x] Task 6: Docs, the contract and the front end's types

Checkpoint after task 6: the slice is done, and the front end's mock compiles against the new types.

## Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| The planner writes to today, or to a hand-placed row | High | Refused in the write query itself; a property test over the pure rule; an API test that reads Today before and after every kind of planner run and compares them byte for byte. |
| Two requests open the same week together and place twice | Med | The user lock is already taken by every caller; the guarded query only places rows still in the bank, so a second run places nothing. |
| Opening a week gets slower | Low | One read for the context and one update per placed task; at most a few dozen a week. |
| Spreading picks different days on two runs of the same state | Med | Ties broken by day, then task id; a test places the same state twice. |

## Decisions (Jan, 2026-11-19)

1. **"Full" means at the cap**: 4 tasks on a Normal day is full. Some days just have to be busy, so nothing is capped or removed; consistent is what matters.
2. **Everything on the day counts towards the cap**, done tasks included; dropped and set-aside ones don't.
3. **More tasks than days** (_n_ > _d_): one on each day, then the rest spread again by the same rule over the lightest days.
4. **A raised target when every day left already holds one of the goal's sessions:** the lightest day left, ties to the earlier.
5. **A goal or item that starts later in the week** isn't placed before its start date.
6. **Task 4 is built here.** The spec leaves "a new fixed-day item due today goes on today" to `recurring-items`, but that slice didn't build it.
7. **The cap stays out of placing.** The spread already prefers the lightest days; skipping full days would be one more automatic rule. Less automation, more left to the person.
8. **`days` is a list of seven on `Week`**, each with its `cap`, so a per-day cap later is an addition, not a change (assumed).
