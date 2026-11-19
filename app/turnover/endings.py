"""How an unfinished task ends, read from the database: the one rule that closing a week and a
late uncheck share (data model, "How a week ends")."""

from datetime import date
from uuid import UUID

from sqlalchemy import Connection

from app.db import models, recurring_items
from app.turnover.due import Ending, ItemSchedule, ending


def schedule_of(item: models.RecurringItem) -> ItemSchedule:
    return ItemSchedule(
        item.schedule_kind,  # type: ignore[arg-type]
        item.starts_on,
        weekday=item.weekday,
        day_of_month=item.day_of_month,
        times=item.times,
        period=item.period,  # type: ignore[arg-type]
    )


def item_of(
    connection: Connection, user_id: UUID, task: models.Task
) -> models.RecurringItem | None:
    if task.recurring_item_id is None:
        return None
    return recurring_items.Querier(connection).get_recurring_item(
        id=task.recurring_item_id, user_id=user_id
    )


def ending_for(connection: Connection, user_id: UUID, task: models.Task, week: date) -> Ending:
    """What closing `week` does to the task if it's unfinished. A recurring task whose item is
    gone ends with its week."""
    if task.origin != "recurring_item":
        return ending(task.origin, None, task.period_start, week)
    item = item_of(connection, user_id, task)
    if item is None:
        return "lapses"
    return ending(task.origin, schedule_of(item), task.period_start, week)
