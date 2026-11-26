# Tasks: Coming up (#52)

Plan: [`plan.md`](plan.md). Spec: [`../specs/coming-up.md`](../specs/coming-up.md).

Every task: write the tests first, run the four checks (`uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run pytest`), then one commit. A task that changes a model or a description runs `uv run python -m app.openapi`; one that changes a query runs `sqlc generate`.

# PR: `coming-up` (closes #52)

### Task 1: `ListDatedTasks` and `nextUp`

**Description:** `ListDatedTasks(user_id, from_day, through_day)` in `db/queries/tasks.sql`; `Week.next_up`, filled in `week_read` for the current week only.

**Acceptance criteria:**
- [ ] `nextUp` is tomorrow's pinned task over next week's due one; a task later today is never it.
- [ ] A task due after Coming up's 12th week isn't it; next week's read and a read with nothing coming have `null`.
- [ ] A done, dropped or recurring task, or one under a paused goal, isn't it.
- [ ] A task set to a day and due earlier is it on its planned day.

**Verify:** `uv run pytest tests/test_week_read.py`, then the four checks.

**Dependencies:** none.

## Checkpoint: after task 1

- [ ] The four checks pass; `openapi.json` changes only by addition.

### Task 2: `getComingUp`

**Description:** `ComingUp` and `ComingUpWeek`; `get_coming_up` (`GET /coming-up`, asks for `Today`); `app/tasks/coming_up.py`; `dated.check_ins`/`deadlines` over a range; `fullness.expected_counts`, pure.

**Acceptance criteria:**
- [ ] Twelve weeks from next week, Mondays in order; on Sunday after 6 p.m. the first is `open`; after a wrap-up they start a week later.
- [ ] Each week's `counts` equals `getWeek`'s, with a target changed for next week and a goal starting in week 3.
- [ ] Listed: a task set to a day five weeks out; one due in week 3 with no row; one in this week's bank due in week 2 (in week 2 only); a one-off goal's step due in week 4; a milestone date and a deadline.
- [ ] Not listed: recurring work, a done or dropped task, a task under a paused goal, a task due this week, a task 13 weeks out.
- [ ] A task set to a day and due in a later week is listed once, on its day.
- [ ] Another user's tasks, milestones and goals never appear (`tests/test_other_user.py`).

**Verify:** `uv run pytest tests/test_coming_up.py tests/test_other_user.py tests/test_any_week.py tests/test_fullness.py`, then the four checks.

**Dependencies:** 1.

## Checkpoint: after task 2

- [ ] Every listed and not-listed case and each `nextUp` case has a test that fails without its rule.

### Task 3: Docs and a check

**Description:** The spec's status and an As built section, the map's row; on a parent-repo branch, `flows.md` flow 9 and the brief's status line. A Sonnet agent runs the four checks and the spec's cases against the running API (port 8000), naming what it creates "Verification: …".

**Acceptance criteria:**
- [ ] The docs say what was built.
- [ ] The agent's checks pass, or what failed is fixed or reported.

**Dependencies:** 2.
