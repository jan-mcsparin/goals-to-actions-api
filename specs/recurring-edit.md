# Spec: Editing a recurring item moves this week's work

Status: built 2026-11-25; decisions settled with Jan the same day, as recommended. The plan is in git history (`tasks/plan.md`). Issue: [#49](https://github.com/jan-mcsparin/goals-to-actions-api/issues/49); its acceptance criteria were settled with Jan on 2026-11-20, and this spec adds recommendations for the three questions it left open (decisions 1 to 3) and one more found while writing it (decision 4). Module `recurring-edit` in the [map](README.md), an addition to `recurring-items`, `week-turnover` and `planner`. The front end's [#76](https://github.com/jan-mcsparin/goals-to-actions-web-frontend/issues/76) (spec [076](../../web-frontend/specs/076-edit-recurring-item.md)) waits on it.

## Objective

When the trash moves from Tuesday to Thursday, this week's trash task moves to Thursday. Today an edit "makes nothing and moves nothing; it takes effect from the item's next period" (`week-turnover`, As built), so the phone shows the old day until next week.

References: [`recurring-items`](recurring-items.md), [`week-turnover`](week-turnover.md) (settled 1, a target changed mid-week), [`planner`](planner.md); [`flows.md`](../../docs/flows.md) flow 4, step 5; [`product-rules.md`](../../docs/product-rules.md) rule 4; ADR-008, ADR-013.

### What changes

`updateRecurringItem` on an active item acts on the item's tasks in every open week, in the same transaction as the edit:

1. **A rename** renames the item's open tasks, in any week, carry-overs and set-aside ones included. Done, dropped and lapsed tasks keep their old title.
2. **The week's tasks are worked out again from the new schedule,** counted from the week's Monday (or `startsOn` if later), so an edit late in the week doesn't make anything done look extra. Each open week's own tasks of the item, done ones included, count towards what the new schedule is due there, and become its tasks (decision 2). Then, like a weekly target change (`week-turnover` settled 1):
   - **too few:** the missing ones are made and placed by the planner on days after today, as new recurring work is now (`fill_item`). With no day after today left, they wait in the bank.
   - **too many:** the extra open ones are removed, last first: the bank before any day, then the latest day. Only ones the app placed or that are in the bank; a task placed by hand or done is never removed. Removed means soft-deleted, so it isn't made again.
3. **A fixed-day task moves to its new day when that day is today or later** (decision 1), if it isn't done and the app placed it or it's in the bank. Otherwise it stays where it is. That one rule covers all four day cases in the issue.
4. **A carry-over from an earlier week is left alone** (decision 3), apart from its title. It isn't this period's task, and it doesn't count towards what this week is due.
5. **A task placed by hand never moves and is never removed.** Done tasks never change, apart from which period they count for.
6. **Nothing is placed on a day before today.** The full-day mark is worked out on the read, as now.
7. **A move to another aspiration, or to none,** moves nothing. It only changes the order the planner serves goals in, which matters for work that arrives later.
8. **An edit to an item that's turned off** renames its open tasks and changes nothing else. **Turning it on** brings its set-aside tasks back to the bank, as now, and then works the week out again from the schedule as in 2 (decision 4).
9. **One transaction and one audit entry** (`update recurring item`). Sending the same edit twice changes nothing more: the second finds the week already matching.

### Not in this

- Changing anything about the request or response: `updateRecurringItem` keeps its body and answer. Only its description changes.
- Moving a task the person placed by hand, or one in a week that has closed.
- Undoing a removal: changing a count back up makes a fresh task.
- The front end (#76).

## The contract

No new routes, models or fields. `openapi.json` changes only in `updateRecurringItem`'s description: "Changes the item. Its open tasks are renamed; this week's tasks, and next week's once it's open, follow the new schedule: fixed-day tasks move to their new day from today on, missing ones are added on later days, and extra open ones are removed. A task placed by hand or done stays."

The phone reads the week again after the edit (spec 076); this write isn't queued.

## Decisions

Settled with Jan, 2026-11-25, as recommended.

1. **An old day still ahead with a new day already past** (on a Wednesday, Thursday → Monday). **Recommended: it stays on Thursday.** The alternatives are the bank, where a fixed-day task can only be placed on its day (#47), which is past, so it would be stuck there until it carries over; or today, which is a guess. Staying keeps one rule for every case: a task moves only when its new day is today or later. It still carries over at the close if it isn't done, as a fixed-day task does.
2. **A change of kind or period** (fixed → flexible, weekly → every two weeks, weekly → monthly). **Recommended: count, don't replace.** The new schedule says how many of the item's tasks each open week holds; the tasks already there count first (done before open), the rest are added or removed as in "What changes" 2. The tasks that stay are renamed in the database to the new schedule's period and number, so opening a later week in the same period doesn't make them again. Weekly Tuesday → 3 times a week, done Tuesday: two more, on later days. Weekly → monthly on the 1st, not due this week: the open task is removed, a done one stays. Only this week's and next week's tasks are counted, never earlier weeks': a monthly flexible task done in the first week of the month, then changed to once every two weeks, gets a fresh one now.
3. **A fixed-day task that carried over from last week.** **Recommended: leave it alone,** apart from its title. It's last period's, the person still owes it, and it's already placed like any task once it carries over. Moving it would be the app deciding the person's plan.
4. **An edit while the item is off** (found while writing). Its tasks are set aside, and moving set-aside tasks would mean nothing. **Recommended: rename only; turning it on works the week out again,** so a schedule changed while it was off takes effect when it comes back, and a task already set aside isn't counted twice.

## Where the code changes

- `app/recurring_items/rules.py`: `update` takes `today` (the route asks for `Today`) and, for an active item, calls the new rule; `turn` calls it after `bring_back`.
- `app/turnover/rules.py`: `fill_item` becomes the rule above, or calls it ("rework_item": rename, count, re-key, move, trim, fill). `trim_goal`'s ordering is shared with the item's trim.
- `db/queries/`: rename an item's open tasks; re-key a generated task (`period_start`, `number`); move a row the app placed to another day; list an item's rows in a week with their state. Then `sqlc generate`.
- `app/recurring_items/routes.py` and `models.py`: `Today` on the route, the description. Then `uv run python -m app.openapi`. `updateRecurringItem` now needs `X-Time-Zone`, as `createRecurringItem` does; the front end already sends it with every request.
- Specs and docs in the same PR: `recurring-items.md` ("Out": what changing a schedule does), `week-turnover.md` (the As built line about edits), `planner.md` (When it runs, 2), this map; `../docs/flows.md` flow 4 (step 3 and step 5).

## Commands

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv run python -m app.openapi
sqlc generate
```

## Testing

Through the `client` fixture against real Postgres, the clock pinned to Wed 18 Nov 2026 and moved with `fixed_clock`; each case in this week and, once open (Sunday 6 p.m.), in next week:

- Rename: an open task, a carry-over and a set-aside one take the new name; a done, a dropped and a lapsed one keep the old.
- Weekly Thursday → Friday: moves. Thursday → Monday (decision 1): stays. Monday → Friday, not done: moves. Monday → Tuesday: stays. Monday, done → Friday: stays done on Monday. Placed by hand on Saturday, Thursday → Friday: stays on Saturday. In the bank, Thursday → Friday: goes on Friday. Thursday → today: goes on today.
- A carry-over from last week, weekly Monday → Friday: stays in the bank (decision 3).
- Monthly day 20 → 25 (both this week) and → 1 (not this week): moves; removed.
- Flexible 2 → 3 a week: one more, after today. 3 → 1 with one done: the two open ones removed, bank first then latest day. 3 → 1 with two placed by hand: both stay.
- Weekly → 3 a week, done: two more. Weekly → once a month: the open task now counts as the month's; opening next week in the same month makes nothing.
- Sunday evening, two weeks open: both weeks follow the edit; today and earlier are untouched.
- Off, edited, turned on: the week matches the new schedule; nothing doubled.
- Aspiration changed: nothing moves.
- The same edit twice; an edit with no change moves nothing; another user's item (404); the audit action. `test_repeats.py` keeps its case, now with the week's rows compared.

## Boundaries

- **Always:** the four checks before saying it's done; docs and specs in the same PR; one PR, `recurring-edit`, closing #49, with the front end's type regeneration in #76's PR.
- **Ask first:** any schema change (none expected); touching a hand-placed task or a closed week.
- **Never:** a write to a hand-placed row; placing anything on a day before today; moving a done task.

## Success criteria

- Every item in "What changes" has a test that fails without the change.
- The four checks pass; `openapi.json` differs only in `updateRecurringItem`'s description and its `X-Time-Zone` header.
- The front end's generated types compile unchanged.

## Open questions

None.

## As built

- **The rule is pure** (`app/turnover/rework.py`) and tested by example (`tests/test_rework.py`); `rework_item` in `app/turnover/rules.py` reads the week, calls it and writes the result. Through the API: `tests/test_item_edits.py`.
- **Only a schedule change reworks the week** (kind, its fields or `startsOn`). A rename or a new aspiration only renames.
- **What a week is due is counted from its Monday** (or `startsOn` if later), so an edit late in the week doesn't make anything done look extra.
- **A week's own tasks** are its rows that didn't roll over into it, plus a flexible task carrying inside the period the schedule before the edit gives that week.
- **Keys:** survivors take the new slots; removed and surplus tasks move to numbers past any in use, in two steps, so the unique index (deleted rows included) is never met. Removed tasks are soft-deleted.
- **Turning on** brings set-aside tasks back, reworks with no new tasks, then fills as before (`fill_item`), so a short week after coming back still gets one task per day left.
- **New queries:** `RenameItemOpenTasks`, `ListItemSlots`, `SetTaskSlot`, `ListItemTasksInWeek`, `MoveItemTask`. `updateRecurringItem` now asks for `Today`, so it needs `X-Time-Zone`.
- **Accepted:** an item turned off, changed, and turned on mid-period may get a fresh flexible task beside one carrying from earlier in the period.
