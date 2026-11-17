# Implementation Plan: Milestones and check-ins (#6)

Spec: [`../specs/milestones-check-ins.md`](../specs/milestones-check-ins.md). Tasks: [`todo.md`](todo.md).

## Overview

The `milestones` and `check_ins` tables; adding, editing and reordering milestones; checking in against Next; keeping a "not yet"; and the goal's page read (milestones, "2 of 6", latest result). After this slice the Aspirations tab, an aspiration's page and a goal's page have everything they read.

One PR, `milestones-check-ins` (closes #6).

## The contract

| Operation | Route | Body | Returns |
| --- | --- | --- | --- |
| `getGoal` | `GET /api/goals/{id}` | | **changes shape:** `{ goal, milestones, progress, latest }` |
| `addMilestone` | `PUT /api/milestones/{id}` | `goalId`, `measurableLine`, `targetDate` (optional) | the goal's page; the milestone goes last |
| `updateMilestone` | `PATCH /api/milestones/{id}` | `measurableLine`, `targetDate`, sent whole | the goal's page |
| `reorderMilestones` | `POST /api/goals/{id}/milestones/reorder` | `ids`: every milestone of the goal, in order | the goal's page |
| `keepMilestone` | `POST /api/milestones/{id}/keep` | | the goal's page |
| `checkIn` | `PUT /api/check-ins/{id}` | `goalId`, `milestoneId` (`null` for the goal's own line), `outcome` (`hit` or `notYet`), `result` (optional) | the goal's page |

**The goal's page** is `goal` (as in slice 3), `milestones` in order (`id`, `position`, `measurableLine`, `targetDate`, `status`: `upcoming`, `hit` or `notYet`), `progress` (`hit` and `of`: the goal's milestones plus one for the goal, which counts as hit once reached), and `latest` (the most recent check-in with a result: `result`, `checkedInOn`; or `null`). Every milestone write returns it, because moving one date can move others, and a check-in can reach the goal.

- **Only Next can be checked in** (`flows.md`, flow 6): the first milestone that isn't hit, or the goal's own line once every milestone is hit. A check-in naming anything else is a 409, so a stale screen can't pass over a milestone. A check-in needs an active or paused goal.
- **A hit sets the milestone to hit; a not yet sets it to not yet.** It stays Next either way until it's hit.
- **A hit on the goal's own line marks the goal reached,** in the same transaction, exactly as `markGoalReached` does (`flows.md`, flow 6 step 4). A not yet on the goal's line is kept as a check-in and changes nothing else.
- **`checkedInOn` is the phone's today**, from `X-Time-Zone`, not sent in the body.
- **The same check-in sent twice** returns the page as it is and adds nothing.
- **Dates:** a milestone's date falls between the goal's start and its deadline (409 otherwise). Moving a date later pushes every later dated milestone out by the same number of days, capped at the deadline; undated ones stay undated, and moving earlier pulls nothing in (`flows.md`, decided Nov 10).
- Milestones only on building and quitting goals: refused by the database, and a 409 from the route. They can be added and edited whatever the goal's status (Go again is "ready to adjust").

## Architecture decisions

- **`milestones` points at `goals (id, user_id, type)`** with `goal_type` in (`building`, `quitting`), as weekly targets do. Position is unique per goal by a deferrable constraint, as aspirations' is; writes that number them take the user lock.
- **`check_ins` points at its milestone and goal together:** `milestones` gets `unique (id, goal_id)`, and `check_ins (milestone_id, goal_id)` references it, so a check-in can't name another goal's milestone. The goal reference carries the owner.
- **"Between start and deadline" is a rule in `rules.py`,** not a constraint: it spans two tables. Tested through the routes.
- **`app/milestones/`** holds the routes, models and rules for milestones and check-ins, and the goal's page read (`goal_page`), which `getGoal` and every milestone write return.
- **No new dependency.**

## Dependency graph

```
1 milestones ──► 2 check_ins
      │                │
      ▼                │
3 add + goal page ──► 4 edit (dates push out; deadline guard) 
      │                │
      ├──► 5 reorder   │
      └──► 6 check in ◄┘──► 7 keep ──► 8 docs and contract
```

## Task list

See [`todo.md`](todo.md).

- [x] 1: The milestones table
- [x] 2: The check_ins table
- [x] 3: Add a milestone, and the goal's page
- [x] 4: Edit a milestone, with dates pushed out
- [x] **Checkpoint A:** milestones can be added and edited; the goal's page reads them; checks pass
- [x] 5: Reorder milestones
- [x] 6: Check in
- [x] 7: Keep a "not yet"
- [x] 8: Docs and the contract
- [x] **Checkpoint B:** every spec criterion met; checks pass; PR opened

## Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| `getGoal` changes shape after slice 3 | Low | The front end isn't wired yet; the #40 comment is updated |
| Pushing dates out and the deadline guard interact | Medium | One function computes the new dates; tests at the cap, with undated milestones between, and moving earlier |
| Reordering puts a hit milestone after one that isn't | Low | Next is always the first not-hit by position, so it stays well defined |

## Decisions to confirm

1. **Move and adjust are `updateMilestone`.** Editing a "not yet" milestone's line or date puts it back to upcoming, which is what move and adjust do. Only keep needs its own route. That's one route fewer than the spec lists, and editing from anywhere answers the card.
2. **A goal's deadline can't be moved before a milestone's date** (spec open question 3): `updateGoal` answers 409. The person moves the milestone first. Pulling dates in silently would change something they didn't touch.
3. **`getGoal` returns the goal's page** (`{ goal, milestones, progress, latest }`), while every goal write keeps returning the goal alone.
4. **The goal's line counts as hit only when the goal is reached,** so a reached goal reads "6 of 6" whatever was passed on the way, and an ended one doesn't count it.
