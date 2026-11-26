"""How full a week is (product rule 11): its tasks counted by origin. Actual for a week that
has opened, from the tasks the week read returns (spec `any-week`)."""

from collections.abc import Iterable
from datetime import date

from app.db.tasks import ListWeekTasksRow
from app.tasks.models import DayCounts, WeekCounts


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
