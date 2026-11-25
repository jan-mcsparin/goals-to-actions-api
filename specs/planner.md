# Spec: The planner

Status: built 2026-11-19, after the plan's questions were answered. Issue: [#10](https://github.com/jan-mcsparin/goals-to-actions-api/issues/10). Module `planner` in the [map](README.md). Depends on `week-turnover`.

## Objective

Place the week's recurring work on days: fixed-day tasks on their day, and a goal's sessions and a flexible item's tasks spread evenly across the week. Everything else stays in the bank for the person to place (ADR-013). It runs on the server (ADR-008), when a week opens and as new recurring work arrives (ADR-009).

The full draft this spec used to describe (due-date placement, fitting under the cap, goals taking turns, lifting work off days when intensity drops) is gone. A wrong guess costs the person more than placing a task themselves.

References: [`product-rules.md`](../../docs/product-rules.md#planning), [`flows.md`](../../docs/flows.md#flow-4-plan-today), [ADR-008](../../docs/adr/0008-planner-on-server.md), [ADR-009](../../docs/adr/0009-week-opens-sunday-drafted-once.md), [ADR-013](../../docs/adr/0013-place-only-recurring-work.md), [`data-model.md`](../../docs/data-model.md#rules-the-data-must-keep).

## Scope

**In:**

- A placing rule, written as a plain function from the week's state (the tasks to place, what is already on each day, the first day it may use) to a list of placements, with no database or clock inside it, so it can be tested by example.
- The two times it runs (below).
- The two things it must never do: move a task placed by hand, or write to today or an earlier day after the week's first placement. Both are also refused where the database can refuse them.
- The full-day mark: the week's read carries each day's cap and whether the day has reached it. It is worked out on every read, and nothing is moved because of it.

**Out:**

- Placing anything that isn't recurring work: tasks added by hand, a one-off goal's steps, tasks now due, carry-overs. They stay in the bank.
- The cap as a limit. Lowering intensity moves nothing (ADR-013).
- Saying the bank holds more than the week can, or suggesting what to move.
- Learning a person's rhythm, time estimates, per-day capacity, calendar awareness.
- Order within a day. Timed tasks anchor a day and untimed ones float around them, but that is how a day is drawn; no position is stored.
- A "suggest a plan" the person asks for. The bank-first design leaves room for it later.

## When it runs

1. **The first placement,** when a week opens (`week-turnover`), in the same transaction. It places the new week's recurring work and may use any day from today on. Opened on Sunday evening, that is the whole week.
2. **New recurring work,** in the transaction that creates it: a new building goal's sessions, a session added by a raised target, a new or changed recurring item's tasks, and sessions or recurring tasks made fresh when a goal or item comes back. It places only the arriving tasks, on days after today. With no day after today left in the week, they stay in the bank. An edited recurring item's own tasks moving to their new day is the edit's write, not the planner's ([`recurring-edit`](recurring-edit.md)).

It never runs because a slot came free, and never for a carry-over: carry-overs arrive in the bank. A task the person sent to the bank, added to the bank, or got back by resuming a goal stays there until they place it.

This is why `task_weeks` needs no extra column: the planner only places tasks created in its own transaction.

## Where it puts things

**What it places:** fixed-day recurring tasks, a building goal's weekly sessions, and flexible recurring tasks. "The days it may use" are those from the first day allowed (above) to Sunday.

1. **A fixed-day task** goes on its day. If that day is before the first day it may use, it goes on the first day. It lands on its day whatever the day already holds.
2. **A goal's sessions, or a flexible item's tasks,** are spread evenly over the days it may use. With _n_ tasks and _d_ days, they go _d_/_n_ days apart, rounded down (3 over 7: Monday, Wednesday, Friday), never two on one day unless _n_ is more than _d_. Where the spacing leaves a choice of starting day, it takes the start whose days hold the fewest tasks; ties go to the earlier start.
3. **New work for a goal or item that already has tasks this week** (a raised target) goes on the lightest day it may use that holds none of that goal's or item's tasks; ties go to the earlier day.

**The order** only decides who sees the lighter days first: fixed-day tasks, then maintenance (flexible items with no aspiration), then goal work in the order of its aspiration's position (an aspiration's goals by when they were made, then its recurring items), then goals with no aspiration or a retired one.

**The cap is not consulted.** A day may end up at or over it; the read marks it full.

### Left to other slices

- **An undated step of a one-off goal** has no row until the person pulls it in or dates it (`tasks-week`).
- **A task added by hand under a building goal** counts towards its target, and no session is removed to make up for it.
- **A new fixed-day item whose day is today** is put on today by the route that creates it, because the person just asked for it (`recurring-items`). It is not a planner write.
- **Intensity** is read for the full-day mark; until `settings-sync` adds `setIntensity`, every user is Normal (4).

## Testing strategy

- **The placing function, by example:** a table of small weeks in, placements out. One case per rule above, plus the empty week, a week first opened on Wednesday, more sessions than days, two goals competing for the lighter days, and a day already over the cap.
- **Properties that must hold:** no hand-placed task moves; after the first placement nothing lands on today or earlier; only recurring work is ever placed; every placement is inside the week; placing the same state twice gives the same placements.
- **Through the API:**
  - a placement when the week opens, on Sunday evening and on a first request midweek;
  - carry-overs, tasks now due and one-off steps are in the bank after the week opens;
  - a new goal made on Tuesday has its sessions on Wednesday or later;
  - a check-off made early and a task sent back to the bank each leave every other row as it was;
  - changing intensity moves nothing and changes only the full-day mark.

## Boundaries

As shared. **Ask first:** any change to a planning rule in `product-rules.md`; placing anything that isn't recurring work. **Never:** a write to a hand-placed row; a write to today or an earlier day after the week's first placement; a run triggered by a slot coming free.

## Success criteria

- [x] When a week opens, its recurring work is on days by the rules above, and everything else is in the bank.
- [x] After the first placement, Today is byte-for-byte the same before and after any planner run.
- [x] New recurring work is placed on later days, and nothing else moves.
- [x] The week's read marks a day at the cap as full; nothing is moved because of it.
- [x] The front end's types are regenerated from the new schema and its mock client compiles against them.
- [x] The four checks pass.

## Open questions

None. The two from the full draft (what the "doesn't fit" suggestion says, and whether intensity rides with this slice) went with it.

## What changed while building

Settled with Jan when the plan was written (`../tasks/plan.md`, 2026-11-19):

- **A day is full at the cap**, not only over it: 4 tasks on Normal. Done tasks count; dropped and set-aside ones don't. The week read carries `days`, seven `{ day, cap, full }`.
- **The cap stays out of placing.** Spreading already prefers the lightest days; skipping full days would be one more automatic rule. Less automation, more left to the person.
- **More tasks than days left:** one on each day, then the rest spread again over the lightest.
- **A raised target when every day left already holds one of the goal's sessions** goes on the lightest day, ties to the earlier.
- **A goal or item that starts later in the week** isn't placed before its start date.
- **A new fixed-day item due today goes on today.** "Left to other slices" gave this to `recurring-items`, which hadn't built it; it was built here, in `fill_item`, as a write the person asked for rather than a planner write. Turning an item back on does the same.

Found while building:

- **The database refuses the two forbidden writes in the planner's one query** (`PlaceGeneratedTask` in `db/queries/planner.sql`): it only places a row still in the bank, not placed by hand and unsettled, on a day on or after the first day allowed. No trigger: the database can't know the phone's today.
- **Opening a week is audited as "open week"** even when no week closes first. Before, an opening with nothing to close was recorded as "close week".
