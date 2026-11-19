"""Tasks: the writes. Each runs inside the caller's transaction. A task's state and its rows
change together; the database checks they agree at commit."""

from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import Connection

from app.db import goals, models, task_weeks, tasks
from app.db.models import TaskWeek
from app.errors import NotAllowed, NotFound
from app.tasks.models import CheckOff, NewTask, Placing, Swap, TaskEdit, ToBank
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


def update(connection: Connection, user_id: UUID, task_id: UUID, edit: TaskEdit) -> None:
    updated = tasks.Querier(connection).update_task(
        tasks.UpdateTaskParams(
            id=task_id,
            user_id=user_id,
            title=edit.title,
            due_date=edit.due_date,
            time_kind=None if edit.time_of_day is None else edit.time_of_day.kind,
            time_of_day=None if edit.time_of_day is None else edit.time_of_day.stored(),
        )
    )
    if updated is None:
        raise NotFound


def check_off(
    connection: Connection, user_id: UUID, task_id: UUID, done: CheckOff, today: date
) -> None:
    """Marks the task and its row in play done. A task with no row in play (a one-off goal's
    waiting step, from the goal's page) gets a done row on the day the phone sent. Sent again,
    it changes nothing more."""
    owner = lock_user(connection, user_id)
    task = get(connection, user_id, task_id)
    if task.state in ("dropped", "lapsed"):
        raise NotAllowed(f"A {task.state} task can't be checked off.")
    rows = list(task_weeks.Querier(connection).list_task_weeks(task_id=task_id, user_id=user_id))
    if task.state == "open":
        weeks = open_weeks(today, owner.planned_through_week)
        row = in_play(rows)
        if row is not None and row.week > weeks.current:
            raise NotAllowed("Next week's tasks can't be checked off until it starts.")
        if row is None:
            week = week_of(done.completed_on)
            existing = next((row for row in rows if row.week == week), None)
            if existing is None:
                add_row(connection, user_id, task_id, week, day=done.completed_on, outcome="done")
            else:
                set_row(connection, user_id, existing, done.completed_on, False, "done")
        else:
            set_outcome(connection, user_id, row, "done")
    tasks.Querier(connection).set_task_done(
        tasks.SetTaskDoneParams(
            id=task_id,
            user_id=user_id,
            completed_at=done.completed_at,
            completed_on=done.completed_on,
            value_logged=done.stored_value(),
        )
    )


def uncheck(connection: Connection, user_id: UUID, task_id: UUID) -> None:
    """Puts a done task's row back in play as it was, on its day or in its bank. Sent again,
    it changes nothing more."""
    lock_user(connection, user_id)
    task = get(connection, user_id, task_id)
    if task.state == "open":
        return
    if task.state != "done":
        raise NotAllowed(f"A {task.state} task can't be unchecked.")
    rows = list(task_weeks.Querier(connection).list_task_weeks(task_id=task_id, user_id=user_id))
    set_outcome(connection, user_id, rows[-1], None)
    tasks.Querier(connection).set_task_open(id=task_id, user_id=user_id)


def get(connection: Connection, user_id: UUID, task_id: UUID) -> models.Task:
    task = tasks.Querier(connection).get_task(id=task_id, user_id=user_id)
    if task is None:
        raise NotFound
    return task


def in_play(rows: list[TaskWeek]) -> TaskWeek | None:
    return next((row for row in rows if row.outcome is None), None)


def set_outcome(connection: Connection, user_id: UUID, row: TaskWeek, outcome: str | None) -> None:
    """Closes a row, or puts it back in play, on the day it had."""
    set_row(connection, user_id, row, row.planned_day, row.placed_by_hand, outcome)


def set_row(
    connection: Connection,
    user_id: UUID,
    row: TaskWeek,
    day: date | None,
    placed_by_hand: bool,
    outcome: str | None,
) -> None:
    task_weeks.Querier(connection).set_task_week(
        task_weeks.SetTaskWeekParams(
            id=row.id,
            user_id=user_id,
            planned_day=day,
            placed_by_hand=placed_by_hand and day is not None,
            outcome=outcome,
        )
    )


def place(
    connection: Connection, user_id: UUID, task_id: UUID, placing: Placing, today: date
) -> None:
    """Puts the task on a day of its week, placed by hand: pulling it from the bank, or moving
    it to another day."""
    owner = lock_user(connection, user_id)
    row = row_in_week(connection, user_id, task_id, placing.week)
    check_day(placing.day, row.week, today, open_weeks(today, owner.planned_through_week))
    set_row(connection, user_id, row, placing.day, True, None)


def move_to_bank(connection: Connection, user_id: UUID, task_id: UUID, to_bank: ToBank) -> None:
    """Clears the task's day. Nothing else changes."""
    lock_user(connection, user_id)
    row = row_in_week(connection, user_id, task_id, to_bank.week)
    set_row(connection, user_id, row, None, False, None)


def row_in_week(connection: Connection, user_id: UUID, task_id: UUID, week: date) -> TaskWeek:
    """The task's row in play, which must be in the week the change was made in."""
    get(connection, user_id, task_id)
    rows = list(task_weeks.Querier(connection).list_task_weeks(task_id=task_id, user_id=user_id))
    row = in_play(rows)
    if row is None:
        raise NotAllowed("The task isn't in play.")
    if row.week != week:
        raise NotAllowed("The task has moved on to another week.")
    return row


def check_day(day: date, week: date, today: date, weeks: OpenWeeks) -> None:
    if week_of(day) != week or not day_allowed(day, today, weeks):
        raise NotAllowed("A task goes on a day from today on, in its own week.")


def swap(connection: Connection, user_id: UUID, task_id: UUID, swap: Swap, today: date) -> None:
    """Trades a task on a day for one from the bank. Both are checked before either
    changes."""
    owner = lock_user(connection, user_id)
    if swap.bank_task_id == task_id:
        raise NotAllowed("A task can't be swapped with itself.")
    to_bank = row_in_week(connection, user_id, task_id, swap.week)
    placed = row_in_week(connection, user_id, swap.bank_task_id, swap.week)
    check_day(swap.day, swap.week, today, open_weeks(today, owner.planned_through_week))
    set_row(connection, user_id, to_bank, None, False, None)
    set_row(connection, user_id, placed, swap.day, True, None)


def drop(connection: Connection, user_id: UUID, task_id: UUID) -> None:
    """ "I decided not to do this." The task stays in history, and its row in play closes.
    Sent again, it changes nothing more."""
    lock_user(connection, user_id)
    task = get(connection, user_id, task_id)
    if task.state == "dropped":
        return
    if task.state != "open":
        raise NotAllowed(f"A {task.state} task can't be dropped.")
    rows = list(task_weeks.Querier(connection).list_task_weeks(task_id=task_id, user_id=user_id))
    row = in_play(rows)
    if row is not None:
        set_outcome(connection, user_id, row, "dropped")
    tasks.Querier(connection).set_task_closed(id=task_id, user_id=user_id, state="dropped")
