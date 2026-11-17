# Implementation Plan: Goals and weekly targets (#5)

Spec: [`../specs/goals-targets.md`](../specs/goals-targets.md). Tasks: [`todo.md`](todo.md).

## Overview

The `goals` and `weekly_targets` tables, the goal routes (list, read, create, edit), the weekly target, the six status changes, and retiring an aspiration with its goals paused. Setting a goal's tasks aside and bringing them back is left to `tasks-week` (shared decision 5): here a status change changes the goal row only.

One PR, `goals-targets` (closes #5), plus a small docs-repo PR if `data-model.md` or `flows.md` need a line.

## The contract

| Operation | Route | Body | Returns |
| --- | --- | --- | --- |
| `listGoals` | `GET /api/goals` | | `{ "goals": [...] }`: under active aspirations by position, then under retired ones, then those with none; within each, by when made |
| `getGoal` | `GET /api/goals/{id}` | | the goal |
| `createGoal` | `PUT /api/goals/{id}` | `type`, `label`, `measurableLine`, `baseline`, `aspirationId`, `startDate`, `deadline`, `weeklyTarget` (building only, and required there) | the goal |
| `updateGoal` | `PATCH /api/goals/{id}` | `label`, `measurableLine`, `baseline`, `aspirationId`, `deadline`, sent whole like `updateAspiration` | the goal |
| `setWeeklyTarget` | `PUT /api/goals/{id}/weekly-target` | `kind`, `sessions`, `amount`, `unit` | the goal |
| `pauseGoal`, `resumeGoal`, `endGoal`, `markGoalReached`, `reopenGoal`, `goAgain` | `POST /api/goals/{id}/pause` and so on | | the goal |
| `retireAspiration` | `POST /api/aspirations/{id}/retire` | gains `itsWork`: `pause` or `keep` | the aspiration |

A goal in JSON: `id`, `aspirationId`, `type` (`building`, `quitting`, `oneOff`), `label`, `measurableLine`, `baseline`, `status`, `startDate`, `deadline`, `endedOn`, `slipped`, `weeklyTarget`, `createdAt`. `weeklyTarget` is the latest row (`kind`, `sessions`, `amount`, `unit`, `effectiveFrom`), so a change waiting for next week shows as one with `effectiveFrom` after this week; `null` for the other types.

- **Reads need `X-Time-Zone`**, because `slipped` (active, with a deadline before today) is worked out on the server. Every request sends the header anyway (decision 9).
- **`startDate` is optional on create** and defaults to today. It isn't editable afterwards.
- **A changed `aspirationId` must be an active aspiration of the same owner** (409 otherwise). Leaving a goal under its retired aspiration is fine.
- **Where the front end's hand-written types differ, the API follows `data-model.md` and #40 adapts:** the weekly target's `kind` and `sessions`, `endedOn` (not `endedAt`), and reopen and go again as their own routes (the mock folds them into `resumeGoal`).

### Status changes

| Route | Allowed from | Sent again (already in the end state) | Otherwise |
| --- | --- | --- | --- |
| pause | active | returns it unchanged | 409 |
| resume | paused | returns it unchanged | 409 |
| end, mark reached | active, paused | returns it unchanged | 409 |
| reopen | reached | returns it unchanged | 409 |
| go again | ended | returns it unchanged | 409 |

`endedOn` is today on end and reached, and cleared by reopen and go again. Resume, reopen and go again work under a retired aspiration (`flows.md`, decided Nov 10). Bringing an aspiration back resumes none of its goals (`flows.md` already says so, which settles open question 2).

### The weekly target's week

A change takes effect in the phone's week, or in the next week once that week is open (`planned_through_week` is later than the phone's week). That column exists but nothing sets it until `week-turnover`, which also adds `closed_through_week` and so finishes the "current week" rule. Here it's one function in `app/weeks.py`, tested by setting `planned_through_week` directly. A second change in the same week replaces the first. A building goal's first target is created with the goal, by the same rule.

## Architecture decisions

- **"Never points at another owner's row" is a foreign key on two columns.** `aspirations` gains `unique (id, user_id)`, and `goals (aspiration_id, user_id)` references it. This is the first table that points at another, so it sets the pattern.
- **"Weekly targets only on building goals" is a foreign key too.** `goals` gets `unique (id, user_id, type)`; `weekly_targets` carries `goal_type text not null default 'building' check (goal_type = 'building')` and references `goals (id, user_id, type)`. A goal's type can't change, so the copy never goes stale.
- **Check constraints:** a status from the four; `ended_on` set exactly when reached or ended; a deadline on or after the start date; the type from the three; a label and line that aren't blank; `effective_from` a Monday; sessions from 1 to 14; an amount above 0 on an amount target and empty on a count; `unique (goal_id, effective_from)`.
- **`app/goals/` follows `app/aspirations/`:** `routes.py`, `models.py`, `rules.py`. Status changes are one rules function driven by the table above, not six copies.
- **Create input is one model with a validator** (`weeklyTarget` required for building, refused otherwise), not a union on `type`, so the generated types stay flat.
- **Writes lock the owner's `users` row,** as aspirations do, so a target change and a goal create sent together don't race.
- **No new dependency.**

## Dependency graph

```
1 goals table ──► 3 create + get + list ──► 4 update
      │                  ▲         │
      ▼                  │         ├──► 6 status changes ──► 7 retire with its work paused
2 weekly_targets ── (app/weeks.py) ┘
                         └──► 5 set weekly target
                                                      all ──► 8 docs and contract
```

## Task list

See [`todo.md`](todo.md).

- [x] 1: The goals table
- [x] 2: The weekly_targets table
- [x] 3: Create, read and list goals
- [x] 4: Edit a goal
- [x] 5: Set the weekly target
- [x] **Checkpoint A:** goals can be made, read, edited and given a new target; checks pass
- [x] 6: The six status changes
- [x] 7: Retiring an aspiration pauses its goals
- [x] 8: Docs and the contract
- [x] **Checkpoint B:** every spec criterion met; checks pass; PR opened

## Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| The target-week rule is half-built until `week-turnover` adds `closed_through_week` | Medium | One function, one place; `week-turnover`'s spec already says it finishes the rule |
| Composite foreign keys get in the way of `delete` (slice 10) | Low | Delete sets `deleted_at` and never removes rows, so the keys hold |
| `retireAspiration` needs a body it didn't have | Low | The front end isn't wired yet (#40); its mock already takes `itsWork` |

## Decisions to confirm

1. **The status-change table above** (spec open question 1). In particular: a paused goal can be ended or marked reached, and an ended goal can't be marked reached without going again first.
2. **`retireAspiration` requires `itsWork`** (`pause` or `keep`), the name the front end's mock already uses. It's required, not defaulted: retire isn't queueable, and the sheet always asks. Recurring items join `pause` in `recurring-items`.
3. **The front end's criterion moves to #40 again,** as with aspirations: there is no type generator in the front end until #40 builds it.
