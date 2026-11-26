"""What a week holds on a date besides its tasks (spec `any-week`): the fixed-day recurring
items a week that hasn't opened would make, worked out and not stored, and the milestone
check-ins and goal deadlines in it."""

from datetime import date
from uuid import UUID

from sqlalchemy import Connection

from app.db import goals, milestones, recurring_items
from app.goals.models import Progress
from app.tasks.models import CheckInDate, GoalDeadline, Occurrence
from app.turnover.due import expected_item_tasks, fixed_day
from app.turnover.endings import schedule_of


def occurrences(connection: Connection, user_id: UUID, week: date) -> list[Occurrence]:
    """Each weekly or monthly item that's on and due in the week, on its day, by day."""
    found = []
    for item in recurring_items.Querier(connection).list_recurring_items(user_id=user_id):
        day = fixed_day(item.schedule_kind, item.weekday, item.day_of_month, week)
        if item.active and day is not None and expected_item_tasks(schedule_of(item), week):
            found.append(Occurrence(recurring_item_id=item.id, title=item.name, day=day))
    return sorted(found, key=lambda occurrence: occurrence.day)


def check_ins(
    connection: Connection, user_id: UUID, from_week: date, through_week: date
) -> list[CheckInDate]:
    rows = milestones.Querier(connection).list_milestone_dates(
        user_id=user_id, from_week=from_week, through_week=through_week
    )
    return [
        CheckInDate(
            goal_id=row.goal_id,
            goal_label=row.goal_label,
            milestone_id=row.id,
            position=row.position,
            of=Progress.counted(row.milestones, 0, "active").of,
            day=row.day,
        )
        for row in rows
    ]


def deadlines(
    connection: Connection, user_id: UUID, from_week: date, through_week: date
) -> list[GoalDeadline]:
    rows = goals.Querier(connection).list_deadlines(
        user_id=user_id, from_week=from_week, through_week=through_week
    )
    return [GoalDeadline(goal_id=row.id, goal_label=row.label, day=row.day) for row in rows]
