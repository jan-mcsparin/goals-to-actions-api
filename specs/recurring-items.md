# Spec: Recurring items

Status: draft 2026-11-13; finalised when its plan is written. Module `recurring-items` in the [map](README.md). Depends on `goals-targets` and `tasks-week`.

## Objective

Maintenance and kept-up practices, with a schedule the server can work with instead of a string. This slice stores and reads them; `week-turnover` makes their tasks.

References: [`data-model.md`](../../docs/data-model.md#recurring_items), [`product-rules.md`](../../docs/product-rules.md#the-model), front-end issue #34.

## Scope

**In:**

- The `recurring_items` table: name, aspiration (optional), from goal (optional), schedule kind (weekly on, monthly on, flexible), weekday, day of month (1 to 28), times and period (flexible: 1 to 6 times a week, once every two weeks, once a month), starts on, active.
- The link from `tasks` to `recurring_items`, with the owner in it.
- Routes: `listRecurringItems` (by aspiration, and Keep life running for those with none), `createRecurringItem`, `updateRecurringItem`, `turnOnRecurringItem`, `turnOffRecurringItem`.
- Worked out on read, never stored: the readable repeat ("Every Tuesday", "3 times a week") and the next due day.
- Keeping a reached goal's practice: creating an item with its from-goal set.
- Retiring an aspiration with its work paused also turns its recurring items off.
- The rule that the schedule's fields fit its kind (a weekly item has a weekday and nothing else), held by a check constraint.

**Out (later):**

- Creating the tasks (`week-turnover`).
- What changing a schedule does to tasks already made for this week (decided there).
- Yearly repeats, "every N weeks", a time of day on an item.
- Delete (`delete`).

## Testing strategy

As shared, plus: one test per schedule kind for the readable repeat and the next due day, including a month boundary, a two-week period anchored on starts-on, and an item that starts in the future; every mismatched combination of schedule fields is refused by the database.

## Boundaries

As shared. **Never:** store the repeat text or the next due day.

## Success criteria

- [ ] Items of all three kinds can be created, edited, turned off and on.
- [ ] The repeat text and next due day are right for each kind.
- [ ] A reached goal can be continued as an item.
- [ ] The four checks pass.

## Open questions

1. **Where does the readable repeat get written, here or in the front end?** It is display text. I'd send the structured schedule and the next due day, and let the front end word it, so copy stays in one place.
2. **Bringing an aspiration back:** do the items its retiring turned off come back on? The front end says they stay off for now. Same answer as the goals question in `goals-targets`.
3. **Turning an item off mid-week:** do its open tasks this week stay, or are they set aside like a paused goal's?
