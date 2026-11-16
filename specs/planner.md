# Spec: The planner

Status: draft 2026-11-13, product decisions settled 2026-11-16; finalised when its plan is written. Issue: [#10](https://github.com/jan-mcsparin/goals-to-actions-api/issues/10). Module `planner` in the [map](README.md). Depends on `week-turnover`.

## Objective

Draft the week: take what is in the bank and put it on days, maintenance first, then goal work, leaving free time. It runs on the server (ADR-008), once per week (ADR-009), and it is the part of the product with the most rules and the most ways to annoy someone.

References: [`product-rules.md`](../../docs/product-rules.md#planning) (all nine planning rules), [`flows.md`](../../docs/flows.md#flow-4-plan-today), [ADR-008](../../docs/adr/0008-planner-on-server.md), [ADR-009](../../docs/adr/0009-week-opens-sunday-drafted-once.md), [`data-model.md`](../../docs/data-model.md#rules-the-data-must-keep).

## Scope

**In:**

- A drafting rule, written as a plain function from the week's state (tasks, what is placed, the first day it may use, intensity) to a list of placements, with no database or clock inside it, so it can be tested by example.
- The three times it runs, and nothing else (below).
- The order, the spread and the cap (below).
- The two things it must never do: move a task placed by hand, or write to today or an earlier day after the week's first draft. Both are also refused where the database can refuse them.
- Saying so when the week holds more than fits: the week's read carries how much of the bank the rest of the week can't hold, which days have room and which are over the cap. It is worked out on every read, and nothing is crammed or moved.

**Out (later):**

- Learning a person's rhythm from history.
- Time estimates, per-day capacity, calendar awareness.
- Intensity that expires.
- Pausing everything while away.
- Order within a day. Timed tasks anchor a day and untimed ones float around them, but that is how a day is drawn; no position is stored.

## Settled 2026-11-16

### When it runs

1. **The first draft,** when a week opens (`week-turnover`), in the same transaction. It places everything in the new week's bank and may use any day from today on. Opened on Sunday evening, that is the whole week.
2. **A new arrival,** in the transaction that creates it: a carry-over when last week closes, a new building goal's sessions, a session added by a raised target, a new or changed recurring item's tasks. Only the arriving tasks are placed, on days after today with room; with no room they stay in the bank.
3. **Intensity lowered:** on days after today that are now over the cap, goal work the planner placed goes back to the bank, lowest priority first, until the day fits. Raising intensity moves nothing.

It never runs because a slot came free. A task checked off early, sent back to the bank, dropped or set aside leaves its day lighter, and the planner leaves it that way. A task the person sent to the bank, added to the bank, or got back by resuming a goal stays in the bank until they place it.

This is why `task_weeks` needs no extra column: the planner only places tasks created or carried over in its own transaction.

### The order

1. **Fixed-day recurring tasks** on their day, even when that takes the day over the cap. If the day is before the first day the draft may use, the first day.
2. **Tasks with a due date in the week:** one with an "at" time on its due date; any other on the lightest day up to its due date. If the date has passed, the first day.
3. **Other maintenance:** flexible recurring tasks and tasks with no goal, on the lightest day with room. Several of one item in a week are spaced apart.
4. **Goal work,** by priority (below).

"Lightest" is the day with the fewest tasks; ties go to the earlier day.

### The cap

- 3 tasks a day at Easing off, 4 at Normal, 6 at Going hard. One constant each; expect to tune them from use.
- Everything on the day counts: placed by hand, placed by the planner, done or not. Quitting answers are not tasks and never count.
- The planner never takes a day past the cap, except for a fixed-day task on its day.
- The person can go past it by hand. The read marks the day as over; nothing is moved.

### Spread and priority

- A goal's sessions are spaced as evenly as the days allow, never two on one day unless there are more sessions than days.
- Goals are taken in the order of their aspirations' positions, then by when the goal was made; goals with no aspiration come last.
- Goals take turns: every goal gets its first session placed before any gets its second. When the week is short, what is left in the bank is the later sessions of the lower goals.

### Left to other slices

- **An undated step of a one-off goal** has no row until the person pulls it in or dates it, so the planner never sees it (`tasks-week`).
- **Unplanned work for a building goal** uses up an open session (`week-turnover`).
- **A new fixed-day item whose day is today** is put on today by the route that creates it, because the person just asked for it (`recurring-items`). It is not a planner write.

## Testing strategy

- **The drafting function, by example:** a table of small weeks in, placements out. One case per rule above, plus the empty week, the full week, the week that doesn't fit, and a week first opened on Wednesday.
- **Properties that must hold for any input:** no hand-placed task moves; after the first draft nothing lands on today or earlier; no day exceeds the cap unless hand-placed or fixed-day tasks take it there; every placement is inside the week; drafting the same state twice gives the same placements. Whether these are written as examples or with a property-testing library is a dependency question to ask in the plan.
- **Through the API:**
  - a draft when the week opens, on Sunday evening and on a first request midweek;
  - a carry-over placed on Tuesday or later;
  - a check-off made early and a task sent back to the bank each leave every other row as it was;
  - lowering intensity lifts only the planner's own goal work.

## Boundaries

As shared. **Ask first:** any change to a planning rule in `product-rules.md`; a property-testing dependency. **Never:** a write to a hand-placed row; a write to today or an earlier day after the week's first draft; filling a day to the cap just because there is room; a run triggered by a slot coming free.

## Success criteria

- [ ] When a week opens, it has a draft that follows every rule above.
- [ ] After the first draft, Today is byte-for-byte the same before and after any planner run.
- [ ] A week that doesn't fit says so and leaves the rest in the bank.
- [ ] A new arrival is placed on a later day with room, and nothing else moves.
- [ ] Lowering intensity lifts goal work off later days over the cap; raising it moves nothing.
- [ ] The front end's types are regenerated from the new schema and its mock client compiles against them.
- [ ] The four checks pass.

## Open questions

1. **What the "doesn't fit" suggestion says.** Rule 9 asks the app to suggest what to move. The read can name the lowest-priority goal work in the bank and the days with room; the wording and whether it names tasks is settled with the front end's screen.
2. **Does intensity ride with this slice?** `settings-sync` asks the same. The planner reads it and reacts to it, so I'd bring `getSettings` and `setIntensity` here.
