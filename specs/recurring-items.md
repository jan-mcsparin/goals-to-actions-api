# Spec: Recurring items

Status: built 2026-11-18. Issue: [#8](https://github.com/jan-mcsparin/goals-to-actions-api/issues/8). Module `recurring-items` in the [map](README.md). Depends on `goals-targets` and `tasks-week`.

## Objective

Maintenance and kept-up practices, with a schedule the server can work with instead of a string. This slice stores and reads them; `week-turnover` works out when they're due and makes their tasks.

References: [`data-model.md`](../../docs/data-model.md#recurring_items), [`product-rules.md`](../../docs/product-rules.md#the-model), front-end issue #34.

## Scope

**In:**

- The `recurring_items` table: name, aspiration (optional), from goal (optional), schedule kind (weekly on, monthly on, flexible), weekday, day of month (1 to 28), times and period (flexible: 1 to 6 times a week, once every two weeks, once a month), starts on, active.
- The link from `tasks` to `recurring_items`, with the owner in it.
- Routes: `listRecurringItems` (by aspiration, and Keep life running for those with none), `createRecurringItem`, `updateRecurringItem`, `turnOnRecurringItem`, `turnOffRecurringItem`.
- The schedule goes out as its fields. The front end words the repeat ("Every Tuesday", "3 times a week"); no screen shows a next due day. Neither is stored.
- `startsOn` is the first day an item can be due, and anchors a two-week period. It doesn't have to fall on the item's weekday or day of month.
- Keeping a reached goal's practice: creating an item with its from-goal set.
- Retiring an aspiration with its work paused also turns its recurring items off. Keeping its work going makes its items maintenance (no aspiration).
- Turning on an item whose aspiration is retired makes it maintenance too.
- Turning an item off, by hand or by retiring, is one state with one effect: its open tasks are set aside in every open week, and turning it on returns them, the way a paused goal's are (`tasks-week`). There are no such tasks until `week-turnover` makes them, so the tests make them in the database directly.
- A flexible item's period is whole weeks: a week; the week of starts-on and the one after, repeating; or the weeks whose Monday falls in a month.
- The read says whether the item is planned as goal work (it has an aspiration) or as maintenance (it has none).
- The rule that the schedule's fields fit its kind (a weekly item has a weekday and nothing else), held by a check constraint.

**Out (later):**

- Creating the tasks (`week-turnover`).
- What changing a schedule does to tasks already made for this week (decided there).
- Which days and periods are due, from the schedule and `startsOn` (`week-turnover`, the first thing that needs it).
- The ending a late uncheck gives a recurring task (`week-turnover`, with the closing rules it reuses).
- Yearly repeats, "every N weeks", a time of day on an item.
- Delete (`delete`).

## Testing strategy

As shared, plus: every mismatched combination of schedule fields is refused by the database and by the request model; off and on with tasks in the bank, on days, placed by hand, done, next week and a closed week; retiring with its work paused and kept. The due-day tests move to `week-turnover`.

## Boundaries

As shared. **Never:** store the repeat text or a next due day.

## Success criteria

- [x] Items of all three kinds can be created, edited, turned off and on.
- [x] The schedule comes back as the fields sent; the front end words it (settled below).
- [x] A reached goal can be continued as an item.
- [x] The front end's types are regenerated from the new schema and its mock client compiles against them.
- [x] The four checks pass.

## The contract, as built

| Operation | Route | Body | Returns |
| --- | --- | --- | --- |
| `listRecurringItems` | `GET /api/recurring-items` | | `{ "recurringItems": [...] }`, on and off, oldest first |
| `createRecurringItem` | `PUT /api/recurring-items/{id}` | `name`, `aspirationId?`, `fromGoalId?`, `schedule`, `startsOn` | the item |
| `updateRecurringItem` | `PATCH /api/recurring-items/{id}` | `name`, `aspirationId`, `schedule`, `startsOn`; sent whole | the item |
| `turnOffRecurringItem` | `POST /api/recurring-items/{id}/turn-off` | | the item |
| `turnOnRecurringItem` | `POST /api/recurring-items/{id}/turn-on` | | the item |

Turning off and on need `X-Time-Zone`.

- **The item:** `id`, `name`, `aspirationId`, `fromGoalId`, `schedule`, `startsOn`, `active`, `createdAt`.
- **The schedule,** one of three shapes told apart by `kind`:
  - `{ "kind": "weekly", "weekday": "tuesday" }`, a weekday by name
  - `{ "kind": "monthly", "dayOfMonth": 1 }`, from 1 to 28
  - `{ "kind": "flexible", "times": 3, "period": "week" }`: 1 to 6 times a `week`, or once (`times` 1) a `twoWeeks` or `month`
- **The list is flat.** The front end groups it by `aspirationId`; none means Keep life running.
- **Errors:** a retired aspiration on create, or moving to one on edit, is a 409; an unknown or another owner's item, aspiration or goal is a 404; a schedule that doesn't fit its kind is a 422.

## Settled

1. **The front end words the repeat** (Jan, 2026-11-18). The API sends the fields; no next due day is sent, since no screen shows one. When an item is due is worked out in `week-turnover`.
2. **Bringing an aspiration back** leaves the items its retiring turned off still off and still under it (flows.md).
3. **Retiring and keeping its work going makes its items maintenance** (Jan, 2026-11-18). Its goals keep their aspiration, as before.
4. **Turning on an item whose aspiration is retired** makes it maintenance, the same end state as keeping its work going.
5. **`startsOn` is the first day an item can be due,** not necessarily a day it's due, so changing the weekday doesn't force a new start.
6. **Retiring with its work paused also sets its goals' tasks aside.** `tasks-week` left this out; it went in with this slice.
7. **Create and every item write take the user lock,** as goal writes do, since retiring changes items too.
8. **The goal an item keeps** must be the owner's; its status isn't checked, so reopening the goal later leaves the item alone.
9. **Unchecking a task whose goal isn't active, or whose item is off, leaves it set aside** (review, 2026-11-18). Before this, an uncheck in an open week put a paused goal's task back on its day.
