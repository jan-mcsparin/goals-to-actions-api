# Spec: On a day

Status: draft 2026-11-23; decisions settled with Jan the same day. Issue: [#50](https://github.com/jan-mcsparin/goals-to-actions-api/issues/50). Module `on-a-day` in the [map](README.md), the first of three from the scheduling brief. Depends on `tasks-week`, `week-turnover` and `planner`. The front end's [#79](https://github.com/jan-mcsparin/goals-to-actions-web-frontend/issues/79) (the Add sheet) builds on it; its #82 (Move and Remove on a future day) uses it once API #51 can read the weeks it shows.

## Objective

Put a task on any day from today on, with an optional time, and it stays there ("the dentist is Dec 12 at 3 p.m."), even in a week that hasn't opened. Move it to another day, in this week or a later one, or drop it. Today a day past the open weeks sends the task to the current week's bank without a word, and a task can't move out of its week.

The row this makes is one the data model already allows: "pinned to a later week", a row for that week with a planned day, placed by hand ([`data-model.md`](../../docs/data-model.md#task_weeks)). Nothing is added to the schema.

References: [brief](../../docs/briefs/scheduling-and-other-weeks.md) ("On a day", suggested work API 1); [`product-rules.md`](../../docs/product-rules.md) rule 10; [`flows.md`](../../docs/flows.md) flow 3, step 2 and "Later weeks"; ADR-009, ADR-010, ADR-013.

### What changes

1. **`addTask` with a `day` from today on, in any week from the current one on,** makes a hand-placed row on that day in that day's week, whether the week has opened or not. A day before today, or in a week before the current one (after a wrap-up), falls back to the current week's bank as now: a create is never refused over where it goes (shared decision 15). The body doesn't change.
2. **`placeTask` can move a task added by hand to a day in another week** (decision 1). The row in play moves: same row, new `week` and `plannedDay`, still placed by hand. `week` in the body stays "the week the change was made in", so a queued move whose task has since left that week is still a 409. The body doesn't change; the rule widens. A goal session or a recurring task still moves only within its own week, and a fixed-day task stays on its day (#47).
3. **`answerStillMatters` with `schedule`** takes the same days as `placeTask`, since it calls it.
4. **`dropTask` on a pinned task** closes its row as dropped, as for any open task (Remove in the design). It already works; this slice tests it.
5. **Opening a week keeps its pinned rows** on their days. `openWeek` adds generated rows only, `listDueTasksWithoutRows` skips a task that has a row, and the planner counts pinned rows as load (`ListWeekPlaces`) and never writes to them (`PlaceGeneratedTask` skips `placed_by_hand`). Tests prove each.
6. **A pinned row in a week nobody opened** is closed with the weeks that are skipped: it rolls over into the current week's bank as one carry-over, like any unfinished hand-added task (`close_weeks` already lists every row in play up to the week closing). `week-turnover`'s "a week nobody opened leaves no rows" is corrected.
7. **The upcoming list leaves pinned tasks out** (it lists tasks with no row). A test proves it, for a pinned task that also has a due date.
8. **A goal paused, ended or reached** sets aside its pinned rows with its other rows from the current week on, as now. **Coming back,** a set-aside row in a week that hasn't opened returns to its day, placed by hand, not to a bank that week doesn't have yet (decision 2). In an open week it goes to the bank, as now.
9. **Checking off a pinned task in a week that hasn't started** is refused (409), as for next week's tasks now.

### Not in this

- Reading any week other than the current and next (API #51). Until then a pinned row in a later week shows on Keep life running ("a later week") and nowhere else; the week read is unchanged.
- Fullness counts (#51), Coming up (#52), late check-offs from a past day (#51).
- A day limit (settled with Jan, 2026-11-23). Any day from today on is allowed; Week and Coming up show 12 weeks ahead, and a task further out shows there once it's within range.

## The contract

No new routes, models or fields. `openapi.json` changes only in descriptions:

| Operation | Change |
| --- | --- |
| `addTask` (`PUT /tasks/{id}`) | `day`: "A day from today on, in this week or a later one. The task is placed there by hand. A day before today goes to the current week's bank." |
| `placeTask` (`POST /tasks/{id}/place`) | `day`: "A day from today on. A task added by hand can go to another week; a generated one stays in its own." |

`placeTask` answers 409 for: a day before today or before the current week; a generated task's day outside its week; a fixed-day task moved off its day; a task no longer in `week`. The front end needs no type change; it regenerates to pick up the descriptions.

## Decisions

Settled with Jan, 2026-11-23.

1. **Only a task added by hand moves between weeks.** A goal session belongs to its week's target, and a recurring task to its item's period (`period_start`, `number`); moved to another week it would count in the wrong one and the week it left would make it again. They keep today's rule: any day of their own week.
2. **A set-aside pinned row comes back on its day.** It was placed by hand, and "tasks the person placed on a day stay there". In a week that hasn't opened there's no bank to return it to.
3. **The row moves; it isn't closed and replaced.** A move is the person changing their mind, not an ending, so it leaves no `rolled_over` row and doesn't count towards "Still matter?". The audit log keeps the old week (ADR-005).
4. **A move across weeks can't meet another row of the task.** One row per task per week (`task_weeks_one_per_week`), and the target is the current week or later, where a task with a row in play has no other row. Should it happen, the answer is a 409, not a 500.

## Where the code changes

- `app/weeks.py` or `app/tasks/rules.py`: `day_allowed` becomes "from today on, in the current week or later"; a separate check keeps a generated task in its week.
- `app/tasks/rules.py`: `landing` (no open-weeks limit for a `day`), `place` (a cross-week move for a task added by hand), `check_day`, `bring_back` (decision 2).
- `db/queries/task_weeks.sql`: `MoveTaskWeek`, setting `week`, `planned_day` and `placed_by_hand` on the row in play. Then `sqlc generate`.
- `app/tasks/models.py`: the two descriptions. Then `uv run python -m app.openapi`.
- Tests: `tests/test_tasks*.py` (add and place across weeks, each refusal), `tests/test_turnover*.py` (opening keeps pinned rows; a skipped week's pinned row carries over once), `tests/test_planner*.py` (pinned rows are load, never moved), `tests/test_goals*.py` (pause and resume a pinned row), `tests/test_repeats.py` (add to a later week twice, move across weeks twice), `tests/test_queued_writes.py` (a queued move after the task left its week).
- Specs and docs in the same PR: `tasks-week.md` (settled 1 replaced), `week-turnover.md` (skipped weeks), `planner.md` (pinned rows are load), this map; `../docs/data-model.md`, `product-rules.md` rule 10, `flows.md` flow 3 (drop "not built" for On a day).

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

Through the `client` fixture, against real Postgres, with the clock pinned (Wed 18 Nov 2026) and moved with `fixed_clock`:

- Add on a day three weeks out: a hand-placed row in that week; the week read for this week doesn't show it; the upcoming list doesn't either.
- Add on yesterday, and on a day of a week a wrap-up closed: the current week's bank.
- Move this week's task to a day in December, and back to tomorrow. Move a pinned task from one later week to another. Move a goal session to next week: 409. Move a fixed-day task: 409. Move with a stale `week`: 409.
- Open the pinned week (move the clock to its Sunday 6 p.m.): the row is where it was, recurring work is placed around it, and a day it fills counts it as load.
- Skip the pinned week entirely (the clock jumps past it): one carry-over into the current week's bank, one `rolled_over` row.
- Pause the task's goal and resume it: back on its day. Drop it: dropped, no row in play.
- Each write twice; another user's task (404).

## Boundaries

- **Always:** the four checks before saying it's done; docs and specs in the same PR; one PR, `on-a-day`, closing #50, with the front end's type regeneration in #79's PR.
- **Ask first:** any schema change (none is expected); widening the move to generated tasks.
- **Never:** a planner write to a pinned row; refusing a queued `addTask` over its day.

## Success criteria

- Every bullet in "What changes" has a test that fails without the change.
- The four checks pass; `openapi.json` differs only in the two descriptions.
- The front end's generated types compile unchanged.

## Open questions

None.
