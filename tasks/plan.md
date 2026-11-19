# Implementation Plan: Recurring items (#8)

Spec: [`../specs/recurring-items.md`](../specs/recurring-items.md). Tasks: [`todo.md`](todo.md).

## Overview

The `recurring_items` table and its routes: create, edit, list, turn off and on. Turning an item off sets its open tasks aside, the way pausing a goal does. Retiring an aspiration now reaches its items: "pause" turns them off, "keep" moves them to Keep life running. No tasks are made yet; `week-turnover` does that.

Six tasks, so **one PR** in the API, `recurring-items` (closes #8), then the front end's types regenerated in its own PR.

## The contract

| Operation | Route | Body | Returns |
| --- | --- | --- | --- |
| `listRecurringItems` | `GET /api/recurring-items` | | `{ "recurringItems": [...] }`, on and off |
| `createRecurringItem` | `PUT /api/recurring-items/{id}` | `name`, `aspirationId?`, `fromGoalId?`, `schedule`, `startsOn` | the item |
| `updateRecurringItem` | `PATCH /api/recurring-items/{id}` | `name`, `aspirationId`, `schedule`, `startsOn`, sent whole | the item |
| `turnOffRecurringItem` | `POST /api/recurring-items/{id}/turn-off` | | the item |
| `turnOnRecurringItem` | `POST /api/recurring-items/{id}/turn-on` | | the item |

**The item:** `id`, `name`, `aspirationId`, `fromGoalId`, `schedule`, `startsOn`, `active`, `createdAt`.

**The schedule** is one of three shapes, told apart by `kind`:

- `{ "kind": "weekly", "weekday": "tuesday" }`
- `{ "kind": "monthly", "dayOfMonth": 1 }`, from 1 to 28
- `{ "kind": "flexible", "times": 3, "period": "week" }`: 1 to 6 times a `week`, or once a `twoWeeks` or `month` (`times` is 1)

There's no repeat text and no next due day. The front end words the repeat from these fields (its #34). Working out which days or periods are due is built in `week-turnover`, the first thing that uses it.

**The list is flat.** The front end groups it by `aspirationId` (none means Keep life running), as it does with `listGoals`. That's one read for the Recurring tab and an aspiration's page.

## Architecture decisions

- **One table, schedule as columns:** `schedule_kind` (text with a check), `weekday` (smallint 1–7, ISO: Monday is 1), `day_of_month` (1–28), `times` (1–6), `period` (`week`, `two_weeks`, `month`), `starts_on`, `active`. One check constraint says which columns each kind fills; the rest are null. Weekdays are names in JSON (`"tuesday"`) so nobody mixes up Sunday-is-0 and Monday-is-1.
- **Foreign keys carry the owner:** `(aspiration_id, user_id)` → aspirations, `(from_goal_id, user_id)` → goals, and `tasks (recurring_item_id, user_id)` → recurring_items, the key `tasks` left for this slice.
- **`startsOn` is the first day the item can be due.** It doesn't have to fall on the weekday or day of month; `week-turnover` takes the first matching day on or after it. It also anchors a two-week period. This loosens the data model's "the day it's first due", so editing the weekday doesn't also force a new start day. The data model is updated to match.
- **Create rules:** the aspiration, if given, is one of the owner's active aspirations (404 if not found, 409 if retired); the from-goal, if given, is the owner's goal (404). The goal's status isn't checked: the offer is made when a goal is reached, and the item stands even if the goal is reopened later. Sent twice, create returns the row as it is.
- **Edit** changes everything but `fromGoalId` and `active`. The same aspiration rule applies. What an edit does to tasks already made is left to `week-turnover`, as the spec says.
- **Off and on reuse the goal code.** `set_aside_goal_tasks` and `bring_back_goal_tasks` take the rows to act on, so a goal's and an item's tasks go through the same code. Off sets the open rows in every open week aside; on returns those whose week is still open. A recurring task from a closed week doesn't come back (it's generated). Both take `lock_user` and are safe to repeat.
- **Turning on an item whose aspiration is retired** clears its aspiration, so it carries on as maintenance. That's the same end state as retiring with "keep".
- **Retiring an aspiration:**
  - "pause": its active items turn off and their tasks are set aside. **This also fixes a gap:** today "pause" pauses the goals but leaves their tasks on the days. Setting those aside goes in the same change.
  - "keep": its items lose their aspiration and become maintenance (Jan, 2026-11-18). Its goals keep theirs, as now.
  - Bringing an aspiration back leaves its items off and unlinked (flows.md).
- **Tests make recurring tasks directly in the database,** with origin `recurring_item`, a period start and a number, because no route makes them yet. That lets off and on be tested here instead of waiting for `week-turnover`.

## Dependency graph

```
recurring_items table + tasks FK (1)
    ├── create + list (2)
    │      └── edit (3)
    └── off / on, set-aside shared with goals (4)
               └── retire reaches items and goal tasks (5)
                        └── docs, openapi.json, front-end types (6)
```

## Task list

- [x] Task 1: The recurring_items table, and the tasks foreign key
- [ ] Task 2: Create and list
- [ ] Task 3: Edit
- [ ] Task 4: Turn off and on
- [ ] Task 5: Retiring an aspiration reaches its items and its goals' tasks
- [ ] Task 6: Docs, the contract and the front end's types

Checkpoint after task 3 (items can be made and edited) and after task 6 (the slice).

## Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Pydantic's union for `schedule` comes out awkward in the generated TypeScript | Med | Use a discriminated union on `kind`. Check the generated type in task 2 and again in the front end in task 6. |
| Sharing the set-aside code changes what pausing a goal does | Med | The goal status tests stay as they are and must pass without edits. |
| `week-turnover` finds `startsOn` meaning the wrong thing | Low | It's written down in the data model and the spec, and that slice's plan rereads it. |

## Decisions (Jan, 2026-11-18)

- The API sends the schedule fields only. No repeat text, no next due day.
- Retire with "keep" clears the items' aspiration.

## Assumed, for review with this plan

- `startsOn` is "can be due from", not "first due" (above).
- Turning on an item whose aspiration is retired clears the aspiration.
- Retire's "pause" now sets its goals' tasks aside too.
