"""The week read, and the task as every task write returns it."""

from collections import Counter
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import Connection

from app.db import aspirations, goals, models, tasks, users, weekly_targets
from app.db.tasks import ListWeekTasksRow
from app.errors import NotFound
from app.goals.models import WeeklyTarget
from app.quitting.record import week_quit_goals
from app.tasks import fullness, progress
from app.tasks.models import DayCounts, DayMark, PlanAspiration, Task, Week, WeekGoal
from app.weeks import WeekStatus, open_weeks, week_status

# Tasks a day holds at each intensity: Easing off, Normal, Going hard.
CAPS = {"easing_off": 3, "normal": 4, "going_hard": 6}


def task_view(connection: Connection, user_id: UUID, task_id: UUID) -> Task:
    row = tasks.Querier(connection).get_task_view(id=task_id, user_id=user_id)
    if row is None:
        raise NotFound
    return Task.from_row(row)


def week_read(connection: Connection, user_id: UUID, week: date, today: date) -> Week:
    owner = users.Querier(connection).get_user(id=user_id)
    assert owner is not None
    weeks = open_weeks(today, owner.planned_through_week, owner.closed_through_week)
    status = week_status(week, weeks)
    rows = list(tasks.Querier(connection).list_week_tasks(user_id=user_id, week=week))
    all_goals = list(goals.Querier(connection).list_goals(user_id=user_id))
    return Week(
        week=week,
        status=status,
        is_current=week == weeks.current,
        next_week_open=weeks.next_open,
        first_week=first_week(connection, user_id),
        tasks=[Task.from_row(row) for row in rows],
        quitting_goals=week_quit_goals(connection, user_id, week, all_goals),
        days=day_marks(week, CAPS[owner.intensity], rows, counted=status != "notOpen"),
        counts=fullness.actual(rows),
        goals=week_goals(connection, user_id, week, status, all_goals),
    )


def first_week(connection: Connection, user_id: UUID) -> date | None:
    first = tasks.Querier(connection).first_row(user_id=user_id)
    return first.week if first else None


def week_goals(
    connection: Connection,
    user_id: UUID,
    week: date,
    status: WeekStatus,
    all_goals: list[models.Goal],
) -> list[WeekGoal]:
    """Progress by status: an open week's active goals with a target; a closed week's goals
    with a target and a session row in it, whatever their status now (spec `any-week`,
    decision 2); none for a week that hasn't opened."""
    if status == "notOpen":
        return []
    targets = progress.targets_for(connection, user_id, week)
    if status == "open":
        shown = [goal for goal in all_goals if goal.status == "active" and goal.id in targets]
    else:
        had = set(
            weekly_targets.Querier(connection).goals_with_sessions(user_id=user_id, week=week)
        )
        shown = [goal for goal in all_goals if goal.id in had and goal.id in targets]
    done = progress.week_progress(connection, user_id, week, targets)
    under = {
        row.id: PlanAspiration.from_columns(row.id, row.name, row.position)
        for row in aspirations.Querier(connection).list_aspirations(user_id=user_id)
    }
    return [
        WeekGoal(
            id=goal.id,
            label=goal.label,
            aspiration=under.get(goal.aspiration_id) if goal.aspiration_id else None,
            weekly_target=WeeklyTarget.from_row(targets[goal.id]),
            progress=done[goal.id],
        )
        for goal in shown
    ]


def day_marks(
    week: date, cap: int, rows: list[ListWeekTasksRow], *, counted: bool
) -> list[DayMark]:
    """Every task the week read returns counts: open or done, on its day. A week that hasn't
    opened has no day counts."""
    load = Counter(row.planned_day for row in rows if row.planned_day is not None)
    counts = fullness.by_day(rows)
    empty = DayCounts(goal_sessions=0, upkeep=0, added=0)
    days = [week + timedelta(days=n) for n in range(7)]
    return [
        DayMark(
            day=day,
            cap=cap,
            full=load[day] >= cap,
            counts=counts.get(day, empty) if counted else None,
        )
        for day in days
    ]
