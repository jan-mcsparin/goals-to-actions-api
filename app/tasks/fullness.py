"""How full a week is (product rule 11): its tasks counted by origin. Actual for a week that
has opened, from the tasks the week read returns; expected for one that hasn't, from the
rules opening uses, with nothing guessed about placement (spec `any-week`)."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import Connection

from app.db import models, recurring_items, tasks
from app.db.tasks import ListPinnedOrDueRow, ListWeekTasksRow
from app.tasks.models import DayCounts, WeekCounts
from app.turnover.due import expected_item_tasks, expected_sessions
from app.turnover.endings import schedule_of
from app.turnover.rules import active_goals


def actual(rows: Iterable[ListWeekTasksRow]) -> WeekCounts:
    """Every task the read returns: in play, done, rolled over or lapsed, the bank included."""
    rows = list(rows)
    sessions = [row for row in rows if row.origin == "weekly_target"]
    return WeekCounts(
        goal_sessions=len(sessions),
        goals=len({row.goal_id for row in sessions}),
        upkeep=sum(row.origin == "recurring_item" for row in rows),
        added=sum(row.origin == "by_hand" for row in rows),
    )


def by_day(rows: Iterable[ListWeekTasksRow]) -> dict[date, DayCounts]:
    """The same tasks by planned day; the bank counts towards the week only."""
    days: dict[date, DayCounts] = {}
    for row in rows:
        if row.planned_day is None:
            continue
        counts = days.setdefault(row.planned_day, DayCounts(goal_sessions=0, upkeep=0, added=0))
        if row.origin == "weekly_target":
            counts.goal_sessions += 1
        elif row.origin == "recurring_item":
            counts.upkeep += 1
        else:
            counts.added += 1
    return days


@dataclass(frozen=True)
class Expecting:
    """What expected counts are worked out from, read once for a range of weeks."""

    goals: list[tuple[models.Goal, int]]
    items: list[models.RecurringItem]
    hand: list[ListPinnedOrDueRow]


def expecting(
    connection: Connection, user_id: UUID, from_week: date, through_week: date
) -> Expecting:
    """The goals and their targets are read as of `from_week`, next week or later: a target
    change takes effect this week or next at the latest (`target_week`), so every later week
    has the same targets."""
    return Expecting(
        goals=active_goals(connection, user_id, from_week),
        items=list(recurring_items.Querier(connection).list_recurring_items(user_id=user_id)),
        hand=list(
            tasks.Querier(connection).list_pinned_or_due(
                user_id=user_id, from_week=from_week, through_week=through_week
            )
        ),
    )


def expected(connection: Connection, user_id: UUID, week: date) -> WeekCounts:
    return expected_counts(week, expecting(connection, user_id, week, week))


def expected_counts(week: date, expecting: Expecting) -> WeekCounts:
    """What opening the week would bring: each active building goal's sessions, each item's
    tasks that are on, and the open tasks added by hand pinned in it or due in it with no row."""
    sessions = {
        goal.id: expected_sessions(count, week, goal.start_date) for goal, count in expecting.goals
    }
    return WeekCounts(
        goal_sessions=sum(sessions.values()),
        goals=sum(count > 0 for count in sessions.values()),
        upkeep=sum(
            expected_item_tasks(schedule_of(item), week) for item in expecting.items if item.active
        ),
        added=sum(row.week == week for row in expecting.hand),
    )
