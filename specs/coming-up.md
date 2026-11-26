# Spec: Coming up

Status: built 2026-11-25; decision 1 settled with Jan the same day, 2 to 5 as assumed. Written with [`any-week`](any-week.md). The plan is in `tasks/plan.md`. Issue: [#52](https://github.com/jan-mcsparin/goals-to-actions-api/issues/52). Module `coming-up` in the [map](README.md), the last of three from the scheduling brief. Depends on `any-week`. The front end's [#83](https://github.com/jan-mcsparin/goals-to-actions-web-frontend/issues/83) (the Coming up page and Today's line) builds on it.

## Objective

The next 12 weeks in one read, for the Coming up page: each week's counts, its check-ins and deadlines, and the things set to a day or due in it. And the one thing Today's last line names: "Coming up: Haircut · Wed at 4:30 p.m. ›".

No new tables or columns. Everything here reuses `any-week`'s counts and dated reads over a range of weeks.

References: [brief](../../docs/briefs/scheduling-and-other-weeks.md) ("Coming up", "Fullness", suggested work API 4); [`flows.md`](../../docs/flows.md) flow 9; [`../../docs/screens/README.md`](../../docs/screens/README.md) (Coming up); ADR-010 (other weeks are read online only, brief settled 3).

### Not in this

- Which weeks start open on the page, trimming, the tap targets' screens: front end #83.
- Recurring work in the list (brief: it shows on each day of the week instead).
- Reminders before a set thing (brief, open question 1).

## The contract

### `getComingUp` (`GET /coming-up`), new

Asks for `Today`. Returns `ComingUp { weeks: ComingUpWeek[] }`: exactly 12 weeks, from the week after the current one (`open_weeks(...).next`), oldest first.

| `ComingUpWeek` field | Type | What |
| --- | --- | --- |
| `week` | `date` | Its Monday. |
| `status` | `"open" \| "notOpen"` | The first is `open` from Sunday evening; the rest are `notOpen`. Same rule as `getWeek`. |
| `counts` | `WeekCounts` | The same numbers `getWeek` gives that week: actual if open, expected if not. |
| `tasks` | `Task[]` | Its dated tasks (below), by day, then time, then as the week read orders them. |
| `checkIns` | `CheckInDate[]` | As `getWeek`'s. |
| `deadlines` | `GoalDeadline[]` | As `getWeek`'s. |

The check-in and deadline counts on line 1 of each row are the lengths of `checkIns` and `deadlines`; no separate fields.

**Dated tasks:** open tasks added by hand (a one-off goal's steps included), under no goal or an active one, listed once each:

- in the week of its planned day, if it has one (set to a day, opened week or not);
- otherwise in the week of its due date, wherever it waits (the upcoming list, this week's bank, an open next week's bank).

A task's day for the page is its planned day, or else its due date: `Task` already carries both. A step reads "Step · {goal}" from `goalLabel` and the goal's type, which the phone has from `listGoals`. A tap goes to the task's day, or to the goal for a check-in or deadline.

Tasks set to or due on a day before next week aren't in Coming up; this week's days show them.

### `getWeek`, one more field

| Field | Type | What |
| --- | --- | --- |
| `nextUp` (new) | `Task \| null` | The current week's read only: the next open task added by hand set to a day, or due, after today and through the last week Coming up shows. Earliest by its day (planned day, else due date), then time, then as the week read orders. Empty in every other week's read, and when there's none. |

## Decisions

Settled with Jan, 2026-11-25.

1. **Today's line comes in the week read** (`nextUp`), not from `getComingUp`. The phone keeps the current week as its one stored document (ADR-010), so Today still opens instantly and the line shows offline; Coming up itself is read online only. A cached `nextUp` whose day has come is left out by the phone until the next read.

Assumed (say so if wrong):

2. **Tasks only on Today's line.** "The next thing set to a day or due" names tasks; a check-in or deadline doesn't take the line.
3. **"After today" means tomorrow on.** Something later today is already on Today.
4. **The line looks no further than Coming up's 12 weeks,** so its › always lands on a page that shows it.
5. **A task in a bank, due later, is listed in its due week and counted in the week of its row** (`any-week`, counts). The list says what's coming; the counts say where the work sits now.

## Where the code changes

- `app/tasks/routes.py`: `get_coming_up` (`getComingUp`), thin: one read, the 12 weeks.
- `app/tasks/coming_up.py` (new): the 12 weeks, from `any-week`'s range queries (`ListPinnedOrDue`, `ListMilestoneDates`, `ListDeadlines`) read once for the whole range and grouped by week, and its counts functions per week. Due tasks already in a bank need the by-hand open tasks with a row in play and a due date; `ListPinnedOrDue` covers them or gains a case.
- `db/queries/tasks.sql`: `NextUp(after, through)`, unless `ListPinnedOrDue` serves it. Then `sqlc generate`.
- `app/tasks/week.py`: `nextUp` on the current week.
- `app/tasks/models.py`: `ComingUp`, `ComingUpWeek`, `Week.next_up`. Then `uv run python -m app.openapi`.
- Tests: `tests/test_coming_up.py`; `tests/test_week_read.py` (`nextUp`); `tests/test_other_user.py` (a case for `getComingUp`, which fails without one).
- Docs in the same PR: `flows.md` flow 9, `product-rules.md` if a rule's status line changes, this spec's status, the map, the brief's status line.

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

- Twelve weeks from next week, Mondays in order; on Sunday after 6 p.m. the first is `open`; after a wrap-up they start a week later.
- Each week's `counts` equals `getWeek`'s for that week.
- Listed: a task set to a day five weeks out; a task due in week 3 with no row; a task in this week's bank due in week 2 (listed in week 2 only); a one-off goal's step due in week 4; a milestone date and a deadline. Not listed: recurring work, a done or dropped task, a task under a paused goal, a task due this week, a task 13 weeks out.
- A task set to a day and due in a later week is listed once, on its day.
- `nextUp`: tomorrow's pinned task over next week's due one; today's task never; none past week 12 of Coming up; empty on next week's read; empty with nothing coming.
- Another user's tasks, milestones and goals never appear.

## Boundaries

- **Always:** the four checks before saying it's done; docs and specs in the same PR; one PR, `coming-up`, closing #52, with the front end's type regeneration in #83's PR; counts from `any-week`'s code, not a copy.
- **Ask first:** any schema change (none is expected); listing recurring work; a write from this read.
- **Never:** a guessed placement for a week that hasn't opened; a query per week where one per range will do.

## Success criteria

- Each listed and not-listed case has a test that fails without its rule.
- `getComingUp`'s counts and `getWeek`'s agree for every week.
- The four checks pass; `openapi.json` changes only by addition.
- The front end's generated types compile, with its mock filling `nextUp` and the new read.

## Open questions

None.

## As built

- **One query for both reads,** `ListDatedTasks(from_day, through_day)`: open tasks added by hand, under no goal or an active one, each on its day (the planned day in play, or else the due date), in the task view's shape. `ListPinnedOrDue` is unchanged: it returns ids and weeks, and counts where the work sits (decision 5).
- **Counts read once for the range.** `fullness.expecting` reads the goals, items and `ListPinnedOrDue` once; the pure `fullness.expected_counts` works out each week. Goals and targets are read as of Coming up's first week: a target change takes effect this week or next at the latest (`target_week`), so every later week has the same targets. An open first week counts with `fullness.actual`, as the week read does.
- **`dated.check_ins` and `dated.deadlines` take a range;** the week read passes its week twice.
- **Coming up's weeks** are `OpenWeeks.coming_up` in `app/weeks.py`; `nextUp` looks through the Sunday of the last.
- **Code:** `app/tasks/coming_up.py`, `get_coming_up` in `app/tasks/routes.py`, `next_up` in `app/tasks/week.py`. Tests: `tests/test_coming_up.py`, `tests/test_week_read.py` (`nextUp`), `tests/test_other_user.py`.
