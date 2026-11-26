"""How full a week is (product rule 11): its tasks counted by origin. Actual for a week that
has opened, from the tasks the week read returns; expected for one that hasn't, from the
rules opening uses, with nothing guessed about placement (spec `any-week`)."""

from collections.abc import Iterable
from datetime import date
from uuid import UUID

from sqlalchemy import Connection

from app.db import recurring_items, tasks
from app.db.tasks import ListWeekTasksRow
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


def expected(connection: Connection, user_id: UUID, week: date) -> WeekCounts:
    """What opening the week would bring: each active building goal's sessions, each item's
    tasks that are on, and the open tasks added by hand pinned in it or due in it with no row."""
    sessions = {
        goal.id: expected_sessions(count, week, goal.start_date)
        for goal, count in active_goals(connection, user_id, week)
    }
    items = recurring_items.Querier(connection).list_recurring_items(user_id=user_id)
    hand = tasks.Querier(connection).list_pinned_or_due(
        user_id=user_id, from_week=week, through_week=week
    )
    return WeekCounts(
        goal_sessions=sum(sessions.values()),
        goals=sum(count > 0 for count in sessions.values()),
        upkeep=sum(expected_item_tasks(schedule_of(item), week) for item in items if item.active),
        added=sum(row.week == week for row in hand),
    )
