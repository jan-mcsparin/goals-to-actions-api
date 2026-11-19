"""What goal reads count from tasks: this week's progress against a weekly target, and a
one-off goal's steps. Each is one query for all of the owner's goals."""

from datetime import date
from uuid import UUID

from sqlalchemy import Connection

from app.db import models, tasks, users, weekly_targets
from app.db.milestones import CountMilestonesRow
from app.goals.models import Progress, WeekProgress
from app.weeks import open_weeks


def current_week(connection: Connection, user_id: UUID, today: date) -> date:
    owner = users.Querier(connection).get_user(id=user_id)
    assert owner is not None
    return open_weeks(today, owner.planned_through_week).current


def targets_for(
    connection: Connection, user_id: UUID, week: date
) -> dict[UUID, models.WeeklyTarget]:
    """Each goal's target for the week, as set on or before it."""
    rows = weekly_targets.Querier(connection).weekly_targets_for(
        user_id=user_id, effective_from=week
    )
    return {row.goal_id: row for row in rows}


def week_progress(connection: Connection, user_id: UUID, week: date) -> dict[UUID, WeekProgress]:
    """Each goal with a target that week: done out of sessions (count), or the values logged
    out of the amount (amount)."""
    done = {
        row.goal_id: row for row in tasks.Querier(connection).week_done(user_id=user_id, week=week)
    }
    progress = {}
    for goal_id, target in targets_for(connection, user_id, week).items():
        row = done.get(goal_id)
        if target.kind == "amount" and target.amount is not None:
            progress[goal_id] = WeekProgress(
                done=float(row.logged) if row else 0.0, of=float(target.amount)
            )
        else:
            progress[goal_id] = WeekProgress(done=row.done if row else 0, of=target.sessions)
    return progress


def steps(connection: Connection, user_id: UUID) -> dict[UUID, tuple[int, int]]:
    """Each one-off goal's steps: (done, not dropped)."""
    return {
        row.goal_id: (row.done, row.steps)
        for row in tasks.Querier(connection).count_steps(user_id=user_id)
    }


def step_progress(counted: tuple[int, int] | None, status: str) -> Progress:
    """ "Step 3 of 6": the steps done, out of the steps not dropped. A reached goal counts
    complete."""
    done, of = counted or (0, 0)
    return Progress(hit=of if status == "reached" else done, of=of)


def goal_progress(
    row: models.Goal, counts: CountMilestonesRow | None, counted_steps: tuple[int, int] | None
) -> Progress:
    """Milestones hit out of milestones and the goal, or a one-off goal's steps."""
    if row.type == "one_off":
        return step_progress(counted_steps, row.status)
    milestones, hit = (counts.milestones, counts.hit) if counts else (0, 0)
    return Progress.counted(milestones, hit, row.status)
