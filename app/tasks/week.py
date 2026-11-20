"""The week read, and the task as every task write returns it."""

from collections import Counter
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import Connection

from app.db import aspirations, goals, tasks, users
from app.errors import NotFound
from app.goals.models import WeeklyTarget
from app.quitting.record import week_quit_goals
from app.tasks import progress
from app.tasks.models import DayMark, PlanAspiration, Task, Week, WeekGoal
from app.weeks import open_weeks

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
    rows = list(tasks.Querier(connection).list_week_tasks(user_id=user_id, week=week))
    targets = progress.targets_for(connection, user_id, week)
    done = progress.week_progress(connection, user_id, week, targets)
    all_goals = list(goals.Querier(connection).list_goals(user_id=user_id))
    active = [goal for goal in all_goals if goal.status == "active" and goal.id in targets]
    under = {
        row.id: PlanAspiration(id=row.id, name=row.name, position=row.position)
        for row in aspirations.Querier(connection).list_aspirations(user_id=user_id)
    }
    return Week(
        week=week,
        is_current=week == weeks.current,
        next_week_open=weeks.next_open,
        tasks=[Task.from_row(row) for row in rows],
        quitting_goals=week_quit_goals(connection, user_id, week, all_goals),
        days=day_marks(week, CAPS[owner.intensity], [row.planned_day for row in rows]),
        goals=[
            WeekGoal(
                id=goal.id,
                label=goal.label,
                aspiration=under.get(goal.aspiration_id) if goal.aspiration_id else None,
                weekly_target=WeeklyTarget.from_row(targets[goal.id]),
                progress=done[goal.id],
            )
            for goal in active
        ],
    )


def day_marks(week: date, cap: int, planned_days: list[date | None]) -> list[DayMark]:
    """Every task the week read returns counts: open or done, on its day."""
    counts = Counter(day for day in planned_days if day is not None)
    days = [week + timedelta(days=n) for n in range(7)]
    return [DayMark(day=day, cap=cap, full=counts[day] >= cap) for day in days]
