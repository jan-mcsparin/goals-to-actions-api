"""Tasks: the writes. Each runs inside the caller's transaction. A task's state and its rows
change together; the database checks they agree at commit."""

from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import Connection

from app.db import goals, task_weeks, tasks
from app.errors import NotAllowed, NotFound
from app.tasks.models import NewTask
from app.users import lock_user
from app.weeks import OpenWeeks, open_weeks, week_of


@dataclass(frozen=True)
class Landing:
    """Where a new task goes: a week's bank (no day), or a day in it."""

    week: date
    day: date | None = None


def add(connection: Connection, user_id: UUID, task_id: UUID, new: NewTask, today: date) -> None:
    """Adds a task by hand. Never refused over where it goes. Sent again, it changes nothing."""
    owner = lock_user(connection, user_id)
    queries = tasks.Querier(connection)
    if queries.get_task(id=task_id, user_id=user_id):
        return
    goal_type = None
    if new.goal_id is not None:
        goal = goals.Querier(connection).get_goal(id=new.goal_id, user_id=user_id)
        if goal is None:
            raise NotFound
        if goal.status != "active":
            raise NotAllowed("A task can only be added to an active goal.")
        goal_type = goal.type
    added = queries.add_task(
        tasks.AddTaskParams(
            id=task_id,
            user_id=user_id,
            title=new.title,
            goal_id=new.goal_id,
            due_date=new.due_date,
            time_kind=None if new.time_of_day is None else new.time_of_day.kind,
            time_of_day=None if new.time_of_day is None else new.time_of_day.stored(),
        )
    )
    if added is None:
        raise NotAllowed("That id is already in use.")
    goes = landing(new, goal_type, today, open_weeks(today, owner.planned_through_week))
    if goes is not None:
        add_row(connection, user_id, task_id, goes.week, day=goes.day, placed_by_hand=True)


def landing(new: NewTask, goal_type: str | None, today: date, weeks: OpenWeeks) -> Landing | None:
    """Where a task added by hand goes. None: it waits with no row, on the upcoming list or
    as a one-off goal's step."""
    if new.day is not None:
        if day_allowed(new.day, today, weeks):
            return Landing(week_of(new.day), new.day)
        return Landing(weeks.current)
    if new.due_date is not None:
        due_week = week_of(new.due_date)
        if due_week <= weeks.current:
            return Landing(weeks.current)
        return Landing(due_week) if due_week in weeks else None
    return None if goal_type == "one_off" else Landing(weeks.current)


def day_allowed(day: date, today: date, weeks: OpenWeeks) -> bool:
    """A task can go on a day from today on, in an open week. When today is before the current
    week (after a wrap-up, or a flight west), that leaves today out."""
    return day >= today and week_of(day) in weeks


def add_row(
    connection: Connection,
    user_id: UUID,
    task_id: UUID,
    week: date,
    *,
    day: date | None = None,
    placed_by_hand: bool = False,
    outcome: str | None = None,
) -> None:
    task_weeks.Querier(connection).add_task_week(
        task_weeks.AddTaskWeekParams(
            id=uuid4(),
            user_id=user_id,
            task_id=task_id,
            week=week,
            planned_day=day,
            placed_by_hand=placed_by_hand and day is not None,
            outcome=outcome,
        )
    )
