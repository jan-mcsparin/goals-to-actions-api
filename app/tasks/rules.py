"""Tasks: the writes. Each runs inside the caller's transaction. A task's state and its rows
change together; the database checks they agree at commit."""

from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import Connection

from app.db import goals, models, recurring_items, task_weeks, tasks
from app.db.models import TaskWeek
from app.db.task_weeks import ListGoalTaskWeeksRow, ListItemTaskWeeksRow
from app.db.turnover import ListRowsToCloseRow
from app.errors import NotAllowed, NotFound
from app.tasks.models import (
    CheckOff,
    NewTask,
    Placing,
    ScheduleIt,
    StillMattersAnswer,
    Swap,
    TaskEdit,
    ToBank,
)
from app.turnover.endings import ending_for
from app.users import lock_user
from app.weeks import OpenWeeks, open_weeks, week_of

# A row of a goal's or an item's open tasks, with the task's origin.
WorkRow = ListGoalTaskWeeksRow | ListItemTaskWeeksRow
Row = TaskWeek | WorkRow | ListRowsToCloseRow


@dataclass(frozen=True)
class Landing:
    """Where a new task goes: a week's bank (no day), or a day in it."""

    week: date
    day: date | None = None


def add(connection: Connection, user_id: UUID, task_id: UUID, new: NewTask, today: date) -> None:
    """Adds a task by hand. Never refused over where it goes: under a goal that isn't active
    (paused on another device while this was queued) it's set aside, and comes back with the
    goal. Sent again, it changes nothing."""
    owner = lock_user(connection, user_id)
    queries = tasks.Querier(connection)
    if queries.get_task(id=task_id, user_id=user_id):
        return
    goal_type, goal_active = None, True
    if new.goal_id is not None:
        goal = goals.Querier(connection).get_goal(id=new.goal_id, user_id=user_id)
        if goal is None:
            raise NotFound
        goal_type, goal_active = goal.type, goal.status == "active"
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
    goes = landing(
        new,
        goal_type,
        today,
        open_weeks(today, owner.planned_through_week, owner.closed_through_week),
    )
    if goes is not None:
        add_row(
            connection,
            user_id,
            task_id,
            goes.week,
            day=goes.day,
            placed_by_hand=True,
            outcome=None if goal_active else "set_aside",
        )


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
    waiting step, from the goal's page) gets a done row on the day the phone sent. A check-off
    that arrives after its week closed still counts: a lapsed task's last row turns to done,
    and one that rolled over is done on its row in the new week. Sent again, it changes
    nothing more."""
    owner = lock_user(connection, user_id)
    task = get(connection, user_id, task_id)
    if task.state == "dropped":
        raise NotAllowed("A dropped task can't be checked off.")
    rows = list(task_weeks.Querier(connection).list_task_weeks(task_id=task_id, user_id=user_id))
    if task.state == "lapsed":
        # Done in a week that has since closed, sent late: the lapse wasn't final.
        set_outcome(connection, user_id, rows[-1], "done")
    elif task.state == "open":
        row = in_play(rows)
        if (
            row is not None
            and row.week
            > open_weeks(today, owner.planned_through_week, owner.closed_through_week).current
        ):
            raise NotAllowed("Next week's tasks can't be checked off until it starts.")
        if row is None:
            mark_done_without_a_row_in_play(connection, user_id, task_id, rows, done.completed_on)
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


def mark_done_without_a_row_in_play(
    connection: Connection, user_id: UUID, task_id: UUID, rows: list[TaskWeek], day: date
) -> None:
    """A waiting step checked off from the goal's page gets a done row on that day, in that
    day's week. A set-aside task whose latest row is in a later week is done on that row, so
    a done task's last row is always done."""
    week = week_of(day)
    if rows and rows[-1].week > week:
        set_outcome(connection, user_id, rows[-1], "done")
        return
    existing = next((row for row in rows if row.week == week), None)
    if existing is None:
        add_row(connection, user_id, task_id, week, day=day, outcome="done")
    else:
        set_row(connection, user_id, existing, day=day, placed_by_hand=False, outcome="done")


def uncheck(connection: Connection, user_id: UUID, task_id: UUID, today: date) -> None:
    """Puts a done task's row back as it was, on its day or in its bank, or set aside there
    if its goal isn't active or its item is off. If that row's week has closed, the task gets
    the ending the week would have given it: rolled over into the current week's bank, or
    lapsed. Sent again, it changes nothing more."""
    owner = lock_user(connection, user_id)
    task = get(connection, user_id, task_id)
    if task.state == "open":
        return
    if task.state != "done":
        raise NotAllowed(f"A {task.state} task can't be unchecked.")
    rows = list(task_weeks.Querier(connection).list_task_weeks(task_id=task_id, user_id=user_id))
    done_row = rows[-1]
    current = open_weeks(today, owner.planned_through_week, owner.closed_through_week).current
    queries = tasks.Querier(connection)
    queries.set_task_open(id=task_id, user_id=user_id)
    in_play = None if work_is_active(connection, user_id, task) else "set_aside"
    if done_row.week >= current:
        set_outcome(connection, user_id, done_row, in_play)
    elif ending_for(connection, user_id, task, done_row.week) == "rolls_over":
        set_outcome(connection, user_id, done_row, "rolled_over")
        add_row(connection, user_id, task_id, current, outcome=in_play)
    else:
        set_outcome(connection, user_id, done_row, "lapsed")
        queries.set_task_closed(id=task_id, user_id=user_id, state="lapsed")


def work_is_active(connection: Connection, user_id: UUID, task: models.Task) -> bool:
    """Whether the task's goal is active, or its recurring item on. A task with neither is
    always in play."""
    if task.goal_id is not None:
        goal = goals.Querier(connection).get_goal(id=task.goal_id, user_id=user_id)
        return goal is not None and goal.status == "active"
    if task.recurring_item_id is not None:
        item = recurring_items.Querier(connection).get_recurring_item(
            id=task.recurring_item_id, user_id=user_id
        )
        return item is not None and item.active
    return True


def get(connection: Connection, user_id: UUID, task_id: UUID) -> models.Task:
    task = tasks.Querier(connection).get_task(id=task_id, user_id=user_id)
    if task is None:
        raise NotFound
    return task


def in_play(rows: list[TaskWeek]) -> TaskWeek | None:
    return next((row for row in rows if row.outcome is None), None)


def set_outcome(connection: Connection, user_id: UUID, row: Row, outcome: str | None) -> None:
    """Closes a row, or puts it back in play, on the day it had."""
    set_row(
        connection,
        user_id,
        row,
        day=row.planned_day,
        placed_by_hand=row.placed_by_hand,
        outcome=outcome,
    )


def set_row(
    connection: Connection,
    user_id: UUID,
    row: Row,
    *,
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
    check_day(
        placing.day,
        row.week,
        today,
        open_weeks(today, owner.planned_through_week, owner.closed_through_week),
    )
    set_row(connection, user_id, row, day=placing.day, placed_by_hand=True, outcome=None)


def move_to_bank(connection: Connection, user_id: UUID, task_id: UUID, to_bank: ToBank) -> None:
    """Clears the task's day. Nothing else changes."""
    lock_user(connection, user_id)
    row = row_in_week(connection, user_id, task_id, to_bank.week)
    to_the_bank(connection, user_id, row)


def to_the_bank(connection: Connection, user_id: UUID, row: Row) -> None:
    """In play, with no day."""
    set_row(connection, user_id, row, day=None, placed_by_hand=False, outcome=None)


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
    check_day(
        swap.day,
        swap.week,
        today,
        open_weeks(today, owner.planned_through_week, owner.closed_through_week),
    )
    to_the_bank(connection, user_id, to_bank)
    set_row(connection, user_id, placed, day=swap.day, placed_by_hand=True, outcome=None)


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


def answer_still_matters(
    connection: Connection, user_id: UUID, task_id: UUID, answer: StillMattersAnswer, today: date
) -> None:
    """ "Still matter?": keep it, put it on a day, or drop it. Keep and schedule start the
    count of rollovers again. Each answer sent again changes nothing more."""
    lock_user(connection, user_id)
    task = get(connection, user_id, task_id)
    if answer.answer == "drop":
        drop(connection, user_id, task_id)
        return
    if task.state != "open":
        raise NotAllowed(f"A {task.state} task can't be asked.")
    if isinstance(answer, ScheduleIt):
        place(connection, user_id, task_id, Placing(week=answer.week, day=answer.day), today)
    tasks.Querier(connection).set_still_matters_answered(
        id=task_id, user_id=user_id, still_matters_answered_on=today
    )


def goal_task_weeks(connection: Connection, user_id: UUID, goal_id: UUID) -> list[WorkRow]:
    return list(
        task_weeks.Querier(connection).list_goal_task_weeks(goal_id=goal_id, user_id=user_id)
    )


def item_task_weeks(connection: Connection, user_id: UUID, item_id: UUID) -> list[WorkRow]:
    return list(
        task_weeks.Querier(connection).list_item_task_weeks(
            recurring_item_id=item_id, user_id=user_id
        )
    )


def set_aside(connection: Connection, user_id: UUID, rows: list[WorkRow], current: date) -> None:
    """A goal leaving active, or a recurring item turned off: its unfinished tasks' rows in
    every open week are set aside. They keep their day, but no day shows them."""
    for row in rows:
        if row.outcome is None and row.week >= current:
            set_outcome(connection, user_id, row, "set_aside")


def bring_back(connection: Connection, user_id: UUID, rows: list[WorkRow], current: date) -> None:
    """A goal resumed, reopened or gone again, or an item turned on. A set-aside task whose
    week is still open returns to that week's bank; one added by hand whose week has closed
    gets a row in the current week's bank. Last week's generated tasks don't come back."""
    latest = {row.task_id: row for row in rows}  # oldest week first, so the last one wins
    for row in latest.values():
        if row.outcome != "set_aside":
            continue
        if row.week >= current:
            to_the_bank(connection, user_id, row)
        elif row.origin == "by_hand":
            add_row(connection, user_id, row.task_id, current)
