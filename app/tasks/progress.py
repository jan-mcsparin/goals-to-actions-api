"""What goal reads count from tasks: this week's progress against a weekly target, and a
one-off goal's steps. Each is one query for all of the owner's goals."""

from datetime import date
from decimal import Decimal
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


def week_progress(
    connection: Connection,
    user_id: UUID,
    week: date,
    targets: dict[UUID, models.WeeklyTarget] | None = None,
) -> dict[UUID, WeekProgress]:
    """Each goal with a target that week. Takes the targets when the caller has read them."""
    if targets is None:
        targets = targets_for(connection, user_id, week)
    done = {
        row.goal_id: row for row in tasks.Querier(connection).week_done(user_id=user_id, week=week)
    }
    return {
        goal_id: measured(target, done[goal_id].done, done[goal_id].logged)
        if goal_id in done
        else measured(target, 0, Decimal(0))
        for goal_id, target in targets.items()
    }


def goal_week_progress(
    connection: Connection, user_id: UUID, goal_id: UUID, week: date
) -> WeekProgress | None:
    """One goal's week, for its page. Empty without a target that week."""
    target = weekly_targets.Querier(connection).goal_weekly_target_for(
        goal_id=goal_id, user_id=user_id, effective_from=week
    )
    if target is None:
        return None
    row = tasks.Querier(connection).goal_week_done(user_id=user_id, week=week, goal_id=goal_id)
    return measured(target, row.done if row else 0, row.logged if row else Decimal(0))


def measured(target: models.WeeklyTarget, done: int, logged: Decimal) -> WeekProgress:
    """Tasks done out of sessions (count), or the values logged out of the amount (amount)."""
    if target.kind == "amount" and target.amount is not None:
        return WeekProgress(done=float(logged), of=float(target.amount))
    return WeekProgress(done=done, of=target.sessions)


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
