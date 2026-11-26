# Tasks: Any week (#51)

Plan: [`plan.md`](plan.md). Spec: [`../specs/any-week.md`](../specs/any-week.md).

Every task: write the tests first, run the four checks (`uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run pytest`), then one commit. A task that changes a model or a description runs `uv run python -m app.openapi`; one that changes a query runs `sqlc generate`.

# PR: `any-week` (closes #51)

### Task 1: Week status, past rows, `firstWeek`

**Description:** `ListWeekTasks` also returns rolled-over and lapsed rows, with the row's outcome; the other `Task` reads select a null one. `Task.weekOutcome`; `Week.status` from `week_status` in `app/weeks.py`; `FirstWeek` and `Week.firstWeek`. A closed week's Progress: goals with a target and a session row that week, whatever their status now (decision 2). A `notOpen` week has no goals.

**Acceptance criteria:**
- [x] A closed week with a done task, a rolled-over hand task and a lapsed session lists all three, `weekOutcome` on two; set-aside and dropped rows stay out.
- [x] Its Progress shows the goal, also after the goal is ended; a goal paused before the week opened isn't shown.
- [x] `status` for a past, the current, next (open and not) and a later week; a skipped past week is `closed` and empty.
- [x] `firstWeek`: empty for a new user, the first row's week (a set-aside row counts), unchanged by a later row.

**Verify:** `uv run pytest tests/test_week_read.py tests/test_any_week.py`, then the four checks.

**Dependencies:** none.

### Task 2: Late check-offs

**Description:** Tests for a check-off and an uncheck sent weeks after the day (spec, "Late check-offs"). No code expected.

**Acceptance criteria:**
- [x] A hand task rolled over twice, checked off from its first week's day: done on its current-week row, `completedOn` that day, the rolled-over rows unchanged; unchecked: back in play.
- [x] A session lapsed two weeks ago, checked off: row and task done, counted in that week's Progress; unchecked: lapsed again.
- [x] A check-off from a closed week's day while next week is open.
- [x] The past week's read after each shows `weekOutcome` and the current `state`.

**Verify:** `uv run pytest tests/test_check_off.py`, then the four checks.

**Dependencies:** 1.

### Task 3: Actual counts

**Description:** `app/tasks/fullness.py`; `WeekCounts` and `DayCounts`; `counts` and `days[].counts` for closed and open weeks, from the tasks the read returns; `null` day counts for a `notOpen` week.

**Acceptance criteria:**
- [x] Goal sessions (and how many goals), upkeep (with or without an aspiration), added (a one-off goal's steps included), by origin.
- [x] Rolled-over and lapsed tasks count; a rolled-over task counts in both weeks; bank tasks count in the week only; an amount target counts its sessions.
- [x] A skipped past week: counts of zero.

**Verify:** `uv run pytest tests/test_any_week.py`, then the four checks.

**Dependencies:** 1.

## Checkpoint: after tasks 1–3
- [x] The four checks pass; `openapi.json` changes only by addition.

### Task 4: Expected counts

**Description:** Pure rules in `app/turnover/due.py` for a goal's and an item's expected tasks (decision 1); `ListPinnedOrDue(from, through)` in `db/queries/tasks.sql`; `fullness.expected` for a `notOpen` week.

**Acceptance criteria:**
- [x] Pure tests (`tests/test_fullness.py`): a goal starting midweek, a weekly and a monthly item, a two-week and a monthly flexible item counted in their first week only, an item starting later.
- [x] Three weeks out: a pinned task, a task due that week with no row, a task in this week's bank due that week (not counted), a paused goal (nothing of it).
- [x] The same setup opened (clock to its Sunday 6 p.m.): actual counts equal the expected ones.

**Verify:** `uv run pytest tests/test_fullness.py tests/test_any_week.py`, then the four checks.

**Dependencies:** 3.

### Task 5: Occurrences, check-ins, deadlines

**Description:** `app/tasks/dated.py`; `ListMilestoneDates(from, through)` and `ListDeadlines(from, through)`; `Occurrence`, `CheckInDate`, `GoalDeadline` and the three `Week` fields.

**Acceptance criteria:**
- [x] A `notOpen` week lists each fixed-day item due in it, on its day; other weeks list none; nothing is stored.
- [x] Check-ins on every week: upcoming and not-yet milestones dated in it, under active goals; a hit one isn't listed; a moved not-yet one is on its new date; `of` matches the goal page.
- [x] Deadlines of active goals in the week; a paused goal's aren't listed.

**Verify:** `uv run pytest tests/test_any_week.py`, then the four checks.

**Dependencies:** 1.

## Checkpoint: after tasks 4–5
- [x] Every row of the status table, each count rule and each decision has a test.

### Task 6: Docs and a check

**Description:** `tests/test_other_user.py` reads a past and a later week. Spec status and As built; `tasks-week.md`, the map; `../docs/product-rules.md` rules 11 and 12, `flows.md` flow 9, `data-model.md` (late check-offs), the brief's status line on a parent-repo branch. A Sonnet agent runs the four checks and the spec's cases against the running API.

**Acceptance criteria:**
- [ ] Another user's rows, milestones and goals never appear in a past or a later week.
- [ ] Every doc describes what was built; the agent's findings are in the PR.

**Verify:** read through; the four checks.

**Dependencies:** 1–5.
