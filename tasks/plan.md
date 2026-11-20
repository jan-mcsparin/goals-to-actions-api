# Implementation Plan: Delete (#12)

Spec: [`../specs/delete.md`](../specs/delete.md). Tasks: [`todo.md`](todo.md). (The plan for #11 is in git history.)

## Overview

Delete is for mistakes. Five routes hide a row and what belongs to it, in one transaction, by setting `deleted_at`. Nothing is removed from the database, and there is no undo. Every read already leaves deleted rows out; this slice adds the routes, lets positions be reused, and proves no read shows a deleted row.

Seven tasks. **One PR** in the API, `delete` (closes #12), and one small PR in the front end for the regenerated types. The front end's #38 builds the screens later.

## The contract

New. None is queueable (ADR-010: delete needs a connection).

| Operation | Route | Returns |
| --- | --- | --- |
| `deleteTask` | `DELETE /api/tasks/{taskId}` | 204 |
| `deleteMilestone` | `DELETE /api/milestones/{milestoneId}` | `GoalPage`, as every milestone write does |
| `deleteGoal` | `DELETE /api/goals/{goalId}` | 204 |
| `deleteAspiration` | `DELETE /api/aspirations/{aspirationId}` | 204 |
| `deleteRecurringItem` | `DELETE /api/recurring-items/{itemId}` | 204 |

Each is safe to repeat: deleting a row that's already deleted gives the same answer and changes nothing. 404 for an id that was never yours. Nothing is refused with 409: anything that exists can be deleted.

What goes along (Jan, 2026-11-19: the spec's open questions 1 and 2 as written, no undo):

| Deleting | Also deletes | Leaves |
| --- | --- | --- |
| A task | Its week records | |
| A milestone | Its check-ins | The goal's other milestones, renumbered |
| A goal | Its tasks and their week records, milestones, check-ins, weekly targets, quit days, urge ratings | A recurring item continued from it, with `from_goal_id` emptied |
| An aspiration | | Its goals and recurring items, with no aspiration; the other active aspirations, renumbered |
| A recurring item | Its open tasks and their week records | Its other tasks (done, dropped, lapsed), with the link to the item emptied; they keep the origin `recurring_item` |

## Architecture decisions

- **Each delete lives in its own slice** (`app/tasks/`, `app/milestones/`, `app/goals/`, `app/aspirations/`, `app/recurring_items/`): the route in `routes.py`, the cascade in `rules.py`. The queries go in each table's file; turnover's `DeleteTask` and `DeleteTaskRows` move to `tasks.sql` and `task_weeks.sql`, since deletes now use them too.
- **Every delete takes the user lock.** Three renumber, and the other two take tasks out of a week the planner and turnover write to.
- **A repeat is found by a query that sees deleted rows** (`<Thing>Deleted`): no live row, but a deleted one of yours, means the delete already happened. Only these queries look past `deleted_at`.
- **Positions ignore deleted rows.** `aspirations_position_unique` and `milestones_position_unique` become deferrable exclusion constraints over rows not deleted, with the same names, so a deleted row's position can be taken. The other unique rules stay: generated tasks deliberately count deleted rows; `task_weeks_one_per_week` and `weekly_targets_one_per_week` only lose rows along with their task or goal, which nothing makes again.
- **A deleted session isn't made again.** Turnover's `ListGeneratedSlots` already counts deleted tasks.
- **No planner run.** Deleting takes things off the plan; it never places anything.

## Dependency graph

```
positions ignore deleted rows (1)
    ├── deleteTask (2)
    │      ├── deleteRecurringItem (3)
    │      └── deleteGoal (5) ── uses deleteMilestone's cascade (4)
    ├── deleteMilestone (4)
    └── deleteAspiration (6)
          └── no read shows a deleted row; docs, contract, front end's types (7)
```

## Task list

- [x] Task 1: Positions ignore deleted rows
- [x] Task 2: Delete a task
- [x] Task 3: Delete a recurring item

Checkpoint after task 3: tasks and items can be deleted; the four checks pass.

- [x] Task 4: Delete a milestone
- [x] Task 5: Delete a goal
- [x] Task 6: Delete an aspiration

Checkpoint after task 6: all five deletes work.

- [x] Task 7: No read shows a deleted row; docs, the contract and the front end's types

Checkpoint after task 7: the slice is done, and the front end's mock compiles against the new types.

## Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| A visible row points at a hidden one (a goal's label on a task, an item's aspiration) | High | Each cascade empties or deletes every link in the same transaction; task 7 deletes one of everything and walks every read. |
| A deleted position blocks renumbering | Med | Task 1's constraints, and a test that deletes the first of three and adds a fourth. |
| Turnover makes a deleted session again | Med | A test deletes a session and opens its week twice. |
| A cascade misses a table added later | Low | Task 7's sweep lists every table, so a new one fails it until it's handled. |

## Assumed, for review with this plan

1. **The routes use `DELETE`**, the first in the API. The alternative was `POST /things/{id}/delete`, like the other actions; `DELETE` says what it is, and the front end only sees the operation's name.
2. **204, except `deleteMilestone`,** which returns the goal's page as every milestone write does. After the other four the screen is gone or its read is fetched again.
3. **A recurring item's dropped and lapsed tasks stay too**, like its done ones: they are decisions and history, not mistakes. Only open tasks go.
4. **Deleting a paused or ended goal, or a retired aspiration, works the same** as an active one.
