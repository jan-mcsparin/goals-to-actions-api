"""The week read, and the task as every task write returns it."""

from datetime import date
from uuid import UUID

from sqlalchemy import Connection

from app.db import tasks, users
from app.errors import NotFound
from app.tasks.models import Task, Week
from app.weeks import open_weeks


def task_view(connection: Connection, user_id: UUID, task_id: UUID) -> Task:
    row = tasks.Querier(connection).get_task_view(id=task_id, user_id=user_id)
    if row is None:
        raise NotFound
    return Task.from_row(row)


def week_read(connection: Connection, user_id: UUID, week: date, today: date) -> Week:
    owner = users.Querier(connection).get_user(id=user_id)
    assert owner is not None
    weeks = open_weeks(today, owner.planned_through_week)
    rows = tasks.Querier(connection).list_week_tasks(user_id=user_id, week=week)
    return Week(
        week=week,
        is_current=week == weeks.current,
        next_week_open=weeks.next_open,
        tasks=[Task.from_row(row) for row in rows],
    )
