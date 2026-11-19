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


def ending_of(
    origin: str,
    item_kind: str | None,
    item_period: str | None,
    period_start: date | None,
    week: date,
) -> Ending:
    """What closing `week` does to an unfinished task, from what the task queries carry: its
    origin, its item's kind and period (none when it has no item), and its period start. A
    recurring task whose item is gone ends with its week."""
    if origin != "recurring_item":
        return ending(origin, None, period_start, week)
    if item_kind is None:
        return "lapses"
    schedule = ItemSchedule(item_kind, week, period=item_period)  # type: ignore[arg-type]
    return ending(origin, schedule, period_start, week)


def ending_for(connection: Connection, user_id: UUID, task: models.Task, week: date) -> Ending:
    """The same, for a task read on its own."""
    item = None
    if task.recurring_item_id is not None:
        item = recurring_items.Querier(connection).get_recurring_item(
            id=task.recurring_item_id, user_id=user_id
        )
    return ending_of(
        task.origin,
        None if item is None else item.schedule_kind,
        None if item is None else item.period,
        task.period_start,
        week,
    )
