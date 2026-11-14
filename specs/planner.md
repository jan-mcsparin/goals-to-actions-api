# Spec: The planner

Status: draft 2026-11-13; finalised when its plan is written. Module `planner` in the [map](README.md). Depends on `week-turnover`.

## Objective

Draft the week: take what is in the bank and put it on days, maintenance first, then goal work, leaving free time. It runs on the server (ADR-008), and it is the part of the product with the most rules and the most ways to annoy someone, so its spec will be the longest once finalised.

References: [`product-rules.md`](../../docs/product-rules.md#planning) (all nine planning rules), [`flows.md`](../../docs/flows.md) (open planner rules), [ADR-008](../../docs/adr/0008-planner-on-server.md), [`data-model.md`](../../docs/data-model.md#rules-the-data-must-keep).

## Scope

**In:**

- A drafting rule, written as a plain function from the week's state (tasks, what is placed, today, intensity) to a list of placements, with no database or clock inside it, so it can be tested by example.
- The order: fixed-day recurring tasks on their day; tasks with a due date by that date; other maintenance; then goal work spread across the week.
- The cap on tasks per day, set by the user's intensity.
- Timed tasks anchor their day; untimed ones float around them.
- The two things it must never do: write to today or an earlier day, or move a task placed by hand. Both are also refused where the database can refuse them.
- Saying so when the week holds more than fits: the week's read carries what didn't fit and a suggestion, and nothing is crammed.
- When it runs, and what a redraft may move.

**Out (later):**

- Learning a person's rhythm from history.
- Time estimates, per-day capacity, calendar awareness.
- Intensity that expires.
- Pausing everything while away.

## Testing strategy

- **The drafting function, by example:** a table of small weeks in, placements out. One case per planning rule, plus the empty week, the full week and the week that doesn't fit.
- **Properties that must hold for any input:** nothing lands on today or earlier; no hand-placed task moves; no day exceeds the cap unless hand-placed tasks alone exceed it; every placement is inside the week. Whether these are written as examples or with a property-testing library is a dependency question to ask in the plan.
- **Through the API:** a draft after turnover; a redraft after a change leaves today as it was.

## Boundaries

As shared. **Ask first:** any change to a planning rule in `product-rules.md`; a property-testing dependency. **Never:** a write to today, an earlier day or a hand-placed row; filling a day to the cap just because there is room.

## Success criteria

- [ ] After turnover, the week has a draft that follows every planning rule.
- [ ] Today is byte-for-byte the same before and after any planner run.
- [ ] A week that doesn't fit says so and leaves the rest in the bank.
- [ ] Changing intensity changes the next draft.
- [ ] The front end's types are regenerated from the new schema and its mock client compiles against them.
- [ ] The four checks pass.

## Open questions

These are product decisions, and the spec can't be finalised without them.

1. **The cap.** How many tasks a day at Easing off, Normal and Going hard? And does a hand-placed task count towards it?
2. **When does it run?** Once when the week is filled, or again after each change ("the plan adjusts continuously")? If again: does a redraft move tasks it placed earlier on later days, or only place what is still in the bank? Moving them means Thursday can change because of something done on Tuesday.
3. **A check-off made early, or a task sent back to the bank:** does the freed slot get refilled?
4. **The two rules `flows.md` lists as open:** does unplanned work use an open session, and when does an undated step of a one-off goal enter a week?
5. **How is goal work spread?** Evenly across the remaining days, or front-loaded, or on the days the person usually does it (later)?
6. **Priority between goals** when the week can't hold everything: by the aspiration's position?
