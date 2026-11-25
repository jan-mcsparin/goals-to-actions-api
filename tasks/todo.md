# Tasks: Editing a recurring item moves this week's work (#49)

Plan: [`plan.md`](plan.md). Spec: [`../specs/recurring-edit.md`](../specs/recurring-edit.md).

Every task: write the tests first, run the four checks (`uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run pytest`), then one commit. A task that changes a route also runs `uv run python -m app.openapi`.

# PR: `recurring-edit` (closes #49)

### Task 1: The pure rule

**Description:** `app/turnover/rework.py`: from one week's tasks of the item, the new slots, the new fixed day and today, what to re-key, move, remove and make.

**Acceptance criteria:**
- [x] Moves: a fixed-day task the app placed, or in the bank, goes to its new day when that day is today or later; otherwise stays. Done and hand-placed never move. A carry-over is never touched.
- [x] Counts: survivors in order (done, by hand, on a day, bank) take the slots; extras removed bank first, then latest day; done and hand-placed never removed; missing slots made.
- [x] Keys: no two tasks end on one key; removed and surplus tasks get numbers past any in use.

**Verify:** `uv run pytest tests/test_rework.py`, then the four checks.

**Dependencies:** none.

### Task 2: Rename, and fixed-day tasks move

**Description:** The queries and `sqlc generate`; `rules.update(…, today)` renames open tasks and, when the schedule changed, reworks each open week; the route asks for `Today`; `openapi.json`.

**Acceptance criteria:**
- [x] Open tasks (carry-overs and set-aside ones too) take the new name; done, dropped and lapsed keep the old.
- [x] The spec's weekly day cases on the week read, including the carry-over and the hand-placed task.
- [x] A rename or an aspiration change alone moves nothing.

**Verify:** `uv run pytest tests/test_item_tasks.py tests/test_recurring_items.py`, then the four checks.

**Dependencies:** 1.

### Task 3: Counts, and a change of kind or period

**Description:** Removing and making through the API, placed by the planner from tomorrow.

**Acceptance criteria:**
- [ ] Flexible 2 → 3, 3 → 1 with one done, 3 → 1 with two by hand; monthly day 20 → 25 and → 1.
- [ ] Weekly → 3 a week (done): two more. Weekly → once a month: the open task counts as the month's; opening next week in the same month makes nothing.
- [ ] Editing back and forth never hits the unique index.

**Verify:** `uv run pytest tests/test_item_tasks.py`, then the four checks.

**Dependencies:** 2.

### Task 4: Off and on; two open weeks; repeats

**Acceptance criteria:**
- [ ] Off, edited (renamed only), turned on: the week matches the new schedule, nothing doubled.
- [ ] Sunday evening: both weeks follow the edit; today and earlier days unchanged.
- [ ] `test_repeats.py`: the same edit twice changes nothing more; audit action `update recurring item`; the lock test still covers `update`.

**Verify:** the four checks.

**Dependencies:** 3.

## Checkpoint: after tasks 1–4
- [ ] The four checks pass; every "What changes" item in the spec has a test.

### Task 5: Docs and a check

**Description:** Spec status and As built; `recurring-items.md`, `week-turnover.md`, `planner.md`, the map; `../docs/flows.md` flow 4 on a parent-repo branch. A Sonnet agent runs the four checks and the spec's cases against the running API (items named "Verification: …").

**Acceptance criteria:**
- [ ] Every doc describes what was built; the agent's findings are in the PR.

**Verify:** read through; the four checks.

**Dependencies:** 1–4.
