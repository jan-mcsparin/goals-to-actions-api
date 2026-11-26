# Implementation Plan: Coming up (#52)

Spec: [`../specs/coming-up.md`](../specs/coming-up.md). Tasks: [`todo.md`](todo.md). (Plans for earlier specs are in git history.)

## Overview

`getComingUp` reads the 12 weeks after the current one: each week's counts (the same as `getWeek`'s), its dated tasks, check-ins and deadlines. The current week's read gains `nextUp`, the one task Today's last line names. One PR in the API, `coming-up`, closing #52; a small docs PR in the parent repo. No schema change. The front end's type regeneration goes in #83's PR.

## Architecture decisions

- **One new query, `ListDatedTasks(from_day, through_day)`,** for both reads. Open tasks added by hand, under no goal or an active one, with their day: the in-play row's planned day, or else (no row, or a row in a bank) the due date, in the range. It returns the task view's columns (the shape of `GetTaskView`, its row the one in play), ordered by day, then time, then created and id, as the week read orders. `ListPinnedOrDue` stays as it is: it returns only ids and weeks, and counts where the work sits, not where it's listed (decision 5).
- **Coming up groups one read per range.** `app/tasks/coming_up.py` reads `ListDatedTasks`, `ListMilestoneDates` and `ListDeadlines` once over the 12 weeks and groups by `week_of(day)`. `dated.check_ins` and `dated.deadlines` take a `from_week` and `through_week`; the week read passes its week twice.
- **Counts through `fullness`, split pure from read.** `fullness.expected` becomes a read of goals, items and `ListPinnedOrDue` plus a pure `expected_counts(week, goals, items, hand_rows)`; Coming up reads each once for the range and calls the pure part per week. The goals and their targets are read once, as of the first week: a target change takes effect this week or next at the latest (`target_week`), so every later week has the same targets, and `expected_sessions` already starts a goal at its start date. The first week, when open, counts with `fullness.actual` from its `ListWeekTasks` rows, as `getWeek` does.
- **`nextUp` from the same query.** In `week_read`, for the current week only: `ListDatedTasks` from tomorrow through the Sunday of Coming up's last week, first row or `null`.

## Tasks

1. **`ListDatedTasks` and `nextUp`.** The query, `sqlc generate`, `Week.next_up`, the week read's tests. (M)
2. **`getComingUp`.** Models, route, `coming_up.py`, the `dated` and `fullness` refactors, `tests/test_coming_up.py`, `tests/test_other_user.py`. (M)
3. **Docs and a check.** Spec status and As built, the map; parent-repo docs (flows.md flow 9, the brief's status line) on a branch; a Sonnet agent runs the checks and the spec's cases against the running API. (S)

## Checkpoints

- After 1: the four checks pass; `openapi.json` changes only by addition.
- After 2: every listed and not-listed case and each `nextUp` case has a test; counts agree with `getWeek` for all 12 weeks.

## Risks

- **Targets read once.** If a later change lets a target take effect beyond next week, Coming up's expected sessions would drift from `getWeek`'s. The "counts agree" test, with a target change for next week, guards it.
- **Front-end mock.** Regenerated types will need `nextUp` in the front end's mock week; that's #83's PR, as the spec says.
