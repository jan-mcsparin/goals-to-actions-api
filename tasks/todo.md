# Tasks: On a day (#50)

Plan: [`plan.md`](plan.md). Spec: [`../specs/on-a-day.md`](../specs/on-a-day.md).

Every task: write the tests first, run the four checks (`uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run pytest`), then one commit. A task that changes a description runs `uv run python -m app.openapi`.

# PR: `on-a-day` (closes #50)

### Task 1: Add on any later day

**Description:** `day_allowed` from today on in the current week or later; `landing` uses it; the `addTask` `day` description; `openapi.json`.

**Acceptance criteria:**
- [x] A day three weeks out: a hand-placed row in that week; this week's read and the upcoming list (with a due date set) leave it out.
- [x] Yesterday, and a day in a week a wrap-up closed: the current week's bank.
- [x] Checking off a task pinned in a week that hasn't started: 409.
- [x] The add sent twice changes nothing more (`test_repeats.py`).

**Verify:** `uv run pytest tests/test_tasks.py`, then the four checks.

**Dependencies:** none.

### Task 2: Move across weeks

**Description:** `MoveTaskWeek` in `db/queries/task_weeks.sql`, `sqlc generate`; `place` moves a task added by hand to another week; generated tasks and `swap` stay in their week; the `placeTask` description; `openapi.json`.

**Acceptance criteria:**
- [x] This week's task to a day in December and back to tomorrow; a pinned task from one later week to another. Still placed by hand, no `rolled_over` row.
- [x] 409: a goal session to next week, a fixed-day task off its day, a stale `week`, a day before today, another row of the task in the target week.
- [x] `answerStillMatters` with `schedule` to a later week.
- [x] Repeats (a move twice), a queued move after the task left its week (`test_queued_writes.py`).

**Verify:** `uv run pytest tests/test_task_moves.py tests/test_still_matters.py`, then the four checks.

**Dependencies:** 1.

## Checkpoint: after tasks 1–2
- [x] The four checks pass; `openapi.json` differs only in the two descriptions.

### Task 3: Opening and skipping a pinned week

**Acceptance criteria:**
- [ ] The clock moved to the pinned week's Sunday 6 p.m.: the row stays on its day, placed by hand; recurring work is placed around it and the day counts it as load.
- [ ] The clock jumps past the pinned week: one `rolled_over` row, the task in the current week's bank.
- [ ] Dropping a pinned task: dropped, no row in play.

**Verify:** `uv run pytest tests/test_open_week.py tests/test_close_week.py tests/test_planner.py`, then the four checks.

**Dependencies:** 1.

### Task 4: A goal paused and resumed

**Description:** `bring_back` returns a set-aside row in a week that hasn't opened to its day; its callers pass the owner's `planned_through_week`.

**Acceptance criteria:**
- [ ] Paused: the pinned row is set aside. Resumed: back on its day, placed by hand.
- [ ] A set-aside task in an open week still goes to the bank.

**Verify:** `uv run pytest tests/test_goal_status.py`, then the four checks.

**Dependencies:** 1.

## Checkpoint: after tasks 1–4
- [ ] The four checks pass; every "What changes" item in the spec has a test.

### Task 5: Docs and a check

**Description:** Spec status and As built; `tasks-week.md`, `week-turnover.md`, `planner.md`, the map; `../docs/data-model.md`, `product-rules.md` rule 10, `flows.md` flow 3 on a parent-repo branch. A Sonnet agent runs the four checks and the spec's cases against the running API (tasks named "Verification: …").

**Acceptance criteria:**
- [ ] Every doc describes what was built; the agent's findings are in the PR.

**Verify:** read through; the four checks.

**Dependencies:** 1–4.
