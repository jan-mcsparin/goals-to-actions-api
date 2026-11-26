# Spec: Any week

Status: draft, 2026-11-25, written with [`coming-up`](coming-up.md); decisions 1 to 3 settled with Jan the same day. Finalised when its plan is written. Issue: [#51](https://github.com/jan-mcsparin/goals-to-actions-api/issues/51). Module `any-week` in the [map](README.md), the second of three from the scheduling brief. Depends on `on-a-day`. The front end's [#80](https://github.com/jan-mcsparin/goals-to-actions-web-frontend/issues/80) (any week), [#82](https://github.com/jan-mcsparin/goals-to-actions-web-frontend/issues/82) (move and remove) and [#81](https://github.com/jan-mcsparin/goals-to-actions-web-frontend/issues/81) (past days) build on it; `coming-up` reuses its counts and its dated reads.

## Objective

`getWeek` reads any week, past or later, and every read says how full the week is. Today it reads any Monday but treats every week as an open one: a past week loses the tasks that rolled over or lapsed, a later week shows its pinned rows and nothing else, and no week has counts.

- **A past week** shows everything that was on it, with how each unfinished task ended (rolled over, lapsed), so a past day can be ticked off late.
- **A week that hasn't opened** shows only what's known (product rule 12): its pinned rows, its fixed-day recurring items worked out from their schedules, milestone check-in dates and goal deadlines. No guessed plan.
- **Every week** carries its counts by origin (product rule 11): actual for an opened week, expected for the rest. An opened week also gives counts per day.
- **How far back:** the read says which week is the first with any rows, so the arrows know where to stop.
- **Late check-offs** from a past day already work (`check_off`, `uncheck`); this slice proves them for the cases a past day adds.

No new tables or columns.

References: [brief](../../docs/briefs/scheduling-and-other-weeks.md) ("Any week", "A past day", "Fullness", suggested work API 2 and 3); [`product-rules.md`](../../docs/product-rules.md) rules 11 and 12; [`flows.md`](../../docs/flows.md) flow 9; [`data-model.md`](../../docs/data-model.md) (late check-offs); ADR-009, ADR-010, ADR-013.

### Not in this

- Coming up and Today's "Coming up" line (`coming-up`, #52).
- A forward limit. The front end stops at 12 weeks ahead; the API reads any Monday.
- A quitting goal's row on a closed week's past day (the front end's #81 decides; the read already carries each week's quit days).
- Moving a fixed-day task for one week (brief, "Notes for the specs"; front end #82's follow-up).

## The week's status

Worked out from the user's markers and the day, as `open_weeks` does now:

| Status | Which weeks | Tasks | Goals (Progress) | Counts | Day counts |
| --- | --- | --- | --- | --- | --- |
| `closed` | Before the current week | Rows done, rolled over or lapsed, and rows still in play (none, once closing has run) | Decision 2 | Actual | Yes |
| `open` | The current week, and next week once open | As now: in play or done | As now | Actual | Yes |
| `notOpen` | Every later week | Its pinned rows | None | Expected | No (`null`) |

A past week nobody opened is `closed` with no rows (its pinned rows carried over): counts of zero, no occurrences. A fixed-day item due in that gap never appears (`flows.md`, "A week you never opened").

## The contract

`GET /weeks/{week}` (`getWeek`) keeps its route and grows the `Week` model by addition. Fields marked new:

| Field | Type | What |
| --- | --- | --- |
| `status` (new) | `"closed" \| "open" \| "notOpen"` | Above. `isCurrent` and `nextWeekOpen` stay. |
| `firstWeek` (new) | `date \| null` | The Monday of the earliest week with any row, whatever its outcome. Empty when there are none. |
| `counts` (new) | `WeekCounts` | `{ goalSessions, goals, upkeep, added }`, all integers. |
| `tasks` | `Task[]` | As the table above. Set-aside and dropped rows are still left out. |
| `goals` | `WeekGoal[]` | As the table above. |
| `days[].counts` (new) | `DayCounts \| null` | `{ goalSessions, upkeep, added }` for the tasks on that day. Empty for a `notOpen` week. `cap` and `full` stay as they are. |
| `occurrences` (new) | `Occurrence[]` | `notOpen` only, else empty: each fixed-day recurring item due that week, `{ recurringItemId, title, day }`. Worked out, not stored. |
| `checkIns` (new) | `CheckInDate[]` | Every week: `{ goalId, goalLabel, milestoneId, position, of, day }` for each milestone dated in the week that isn't hit yet, under an active goal (decision 3). `position` and `of` read "Milestone 3 of 4", `of` counted as the goal's page counts it (milestones and the goal). |
| `deadlines` (new) | `GoalDeadline[]` | Every week: `{ goalId, goalLabel, day }` for each active goal whose deadline falls in it (decision 3). |
| `quittingGoals` | | Unchanged. |

`Task` gets one field, by addition:

| Field | Type | What |
| --- | --- | --- |
| `weekOutcome` (new) | `"rolledOver" \| "lapsed" \| null` | How the week read's row ended for this task. Empty for a row in play or done, and in every task write's answer. A rolled-over task checked off late reads `rolledOver` here and `done` in `state`. |

`checkIns` and `deadlines` are on every week because it's one rule and no branch; Week shows them only on a week that hasn't opened, and Coming up counts them. Check-ins and deadlines are never counted in `counts`.

`checkOffTask` and `uncheckTask`: no change, beyond their descriptions saying a late one can come from any past day.

## Counts

Tasks are counted by origin: `weekly_target` is goal sessions, `recurring_item` is upkeep (with or without an aspiration), `by_hand` is added (a one-off goal's steps included). `goals` is how many goals the goal sessions are for. Amount targets count their sessions, as every target has a number of sessions.

**Actual** (`closed`, `open`): every task the read returns (in play, done, rolled over, lapsed), so the counts, the list and the full-day mark agree. A task that rolled over counts in both weeks it was in. Day counts are the same tasks, by planned day; the bank counts towards the week only.

**Expected** (`notOpen`), what opening the week would bring, with nothing guessed about placement:

- **Goal sessions:** for each active building goal with a target that week, the sessions opening would make (`goal_slots(sessions, week, max(start_date, week))`, so a goal starting midweek has fewer). `goals` counts those with at least one.
- **Upkeep:** for each recurring item that's on, the tasks opening would make (`item_slots(schedule, week, max(starts_on, week))`). A flexible item with a two-week or monthly period counts in its period's first week only (decision 1), where opening makes it.
- **Added:** open tasks added by hand that have a row in play that week (pinned), and open tasks added by hand with no row, due that week, under no goal or an active one (the rule opening uses, `ListDueTasksWithoutRows`). A task already in a week's bank counts there, not in the later week it's due.

The expected rules live in one pure function each, beside `app/turnover/due.py`'s, so they can't drift from what opening does. `coming-up` calls the same code for its 12 weeks.

## Decisions

Settled with Jan, 2026-11-25.

1. **A flexible item with a longer period counts in its period's first week.** That's where opening makes its task; inside the period it rolls over. Counting it in every week would show a once-a-month item as four tasks.
2. **A past week's Progress shows every goal with a target that week and at least one session row in it**, whatever its status now. Goal status history isn't stored (ADR-005), and a goal paused or ended since still had that week. A goal with no sessions that week (paused before it opened) isn't shown.
3. **Check-ins and deadlines are listed for active goals only,** the goals that make sessions. A paused goal's dates show again once it's resumed.

Assumed (say so if wrong):

4. **`weekOutcome` on `Task`, not a new task type.** The front end draws a past day from the same `Task` it already knows; every other read leaves it empty.
5. **`firstWeek` counts rows of any outcome,** set aside and dropped included, so the first week with anything at all is reachable even if it reads empty.
6. **Hit milestones aren't listed;** `upcoming` and `not_yet` ones with a date are. A not-yet milestone moved to a new date shows on the new date.

## Late check-offs

The rules exist (`check_off`, `uncheck` in `app/tasks/rules.py`; `data-model.md`, "How a week ends") and have tests for a check-off sent the Monday after. A past day adds checks sent weeks later. New tests, no code expected:

- A by-hand task that rolled over twice, checked off from its first week's day: done on its row in the current week; `completedOn` is that past day; the two rolled-over rows stay as they were.
- A goal session that lapsed two weeks ago, checked off: its row and task turn to done, and it counts in that week's Progress.
- Unchecking each: the rolled-over one goes back in play in the current week; the lapsed one lapses again.
- A check-off from a closed week's day while next week is open (Sunday evening).
- The past week's read after each: the task shows with `weekOutcome` and its current `state`.

If one fails, the fix is in this slice; the spec gets an "As built" note.

## Where the code changes

- `db/queries/tasks.sql`: `ListWeekTasks` also returns rolled-over and lapsed rows, with `task_weeks.outcome`; other `Task` reads select a null outcome. New: `FirstWeek`; `ListPinnedOrDue(from, through)` (open by-hand tasks pinned in, or due in and without a row, a range of weeks).
- `db/queries/milestones.sql`: `ListMilestoneDates(from, through)`, with the goal's label and milestone count. `db/queries/goals.sql`: `ListDeadlines(from, through)`.
- `db/queries/weekly_targets.sql` or `tasks.sql`: the goals with session rows in a week (decision 2).
- Every query takes a range of days, so `coming-up` reads 12 weeks in one call each. Then `sqlc generate`.
- `app/turnover/due.py`: the expected counts' pure rules (sessions, item tasks with decision 1).
- `app/tasks/week.py`: `week_read` by status; `day_marks` with counts. A new `app/tasks/fullness.py` (actual and expected counts) and `app/tasks/dated.py` (occurrences, check-ins, deadlines) if `week.py` grows past a screen.
- `app/tasks/models.py`: `WeekCounts`, `DayCounts`, `Occurrence`, `CheckInDate`, `GoalDeadline`, the new fields. Then `uv run python -m app.openapi`.
- Tests: `tests/test_week_read.py` (or a new `tests/test_any_week.py`), `tests/test_fullness.py` for the pure rules, `tests/test_check_off.py` (late check-offs), `tests/test_other_user.py` (another user's rows never show in any status).
- Docs in the same PR: `product-rules.md` rules 11 and 12 ("built in the API"), `flows.md` flow 9, `data-model.md` (late check-offs from a past day), this spec's status, the map, the brief's status line.

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

Through the `client` fixture, against real Postgres, with the clock pinned (Wed 18 Nov 2026) and moved with `fixed_clock`. Week by status:

- **Closed:** a week with a done task, a rolled-over hand task and a lapsed session: all three listed, `weekOutcome` set on two, actual counts and day counts, Progress for the goal (decision 2), including after the goal is ended.
- **Closed, skipped:** a week nobody opened reads empty, counts zero, no occurrences, even with a weekly item due in it.
- **Open:** the current week reads as now plus counts; a goal with an amount target counts its sessions.
- **Not open:** three weeks out, with a pinned task, a weekly and a monthly item, a two-week flexible item (counted in its first week only), a goal with a target and one starting midweek, a task due that week with no row, a task in this week's bank due that week (not counted there), a paused goal (nothing of it), a milestone and a deadline. Expected counts, occurrences, check-ins and deadlines; no goals, `null` day counts.
- **Not open, then opened:** move the clock to its Sunday 6 p.m. and the actual counts match the expected ones for the same setup (the test that keeps the two rules together), apart from what the person changed.
- `firstWeek`: empty for a new user; the first row's week after adding one; unchanged by a later week.
- Check-ins: a hit milestone isn't listed; a not-yet one moved to a later date is listed on the new date; `of` matches the goal page's progress.
- Another user's rows, milestones and goals never appear (`tests/test_other_user.py` already covers the route; this adds a later and a past week).

## Boundaries

- **Always:** the four checks before saying it's done; docs and specs in the same PR; one PR, `any-week`, closing #51, with the front end's type regeneration in #80's PR; the expected rules shared with opening, not copied.
- **Ask first:** any schema change (none is expected); counting anything that isn't a task; a guessed placement for a week that hasn't opened.
- **Never:** a write from a read; storing a fixed-day occurrence; a week read refusing a Monday because it's far away.

## Success criteria

- Each row of the status table, each count rule and each decision has a test that fails without it.
- The expected counts for a week equal its actual counts once it opens, for the same data.
- The four checks pass; `openapi.json` changes only by addition (new fields and models, descriptions).
- The front end's generated types compile, with its mock filling the new fields.

## Open questions

None.
