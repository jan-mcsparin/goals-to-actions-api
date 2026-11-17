"""Goals: the writes that need more than one query. Each runs inside the caller's
transaction."""

from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import Connection

from app.db import aspirations, goals, models, users, weekly_targets
from app.errors import NotAllowed, NotFound
from app.goals.models import TYPE_IN_DATABASE, GoalEdit, NewGoal, WeeklyTargetInput
from app.weeks import target_week


def create(
    connection: Connection, user_id: UUID, goal_id: UUID, new: NewGoal, today: date
) -> tuple[models.Goal, models.WeeklyTarget | None]:
    """Adds the goal, and a building goal's first target. Sent again, it returns the goal as
    it is."""
    owner = lock_user(connection, user_id)
    queries = goals.Querier(connection)
    existing = queries.get_goal(id=goal_id, user_id=user_id)
    if existing:
        return existing, latest_target(connection, user_id, goal_id)
    if new.aspiration_id is not None:
        check_aspiration(connection, user_id, new.aspiration_id)
    start_date = new.start_date or today
    if new.deadline is not None and new.deadline < start_date:
        raise NotAllowed("A deadline can't be before the start date.")
    created = queries.create_goal(
        goals.CreateGoalParams(
            id=goal_id,
            user_id=user_id,
            aspiration_id=new.aspiration_id,
            type=TYPE_IN_DATABASE[new.type],
            label=new.label,
            measurable_line=new.measurable_line,
            baseline=new.baseline,
            start_date=start_date,
            deadline=new.deadline,
        )
    )
    if created is None:
        raise NotAllowed("That id is already in use.")
    target = None
    if new.weekly_target is not None:
        week = target_week(today, owner.planned_through_week)
        target = set_target(connection, user_id, goal_id, new.weekly_target, week)
    return created, target


def update(
    connection: Connection, user_id: UUID, goal_id: UUID, edit: GoalEdit
) -> tuple[models.Goal, models.WeeklyTarget | None]:
    """Changes what the person typed. A goal can stay under its retired aspiration, but can't
    be moved under one."""
    lock_user(connection, user_id)
    queries = goals.Querier(connection)
    goal = queries.get_goal(id=goal_id, user_id=user_id)
    if goal is None:
        raise NotFound
    if edit.aspiration_id is not None and edit.aspiration_id != goal.aspiration_id:
        check_aspiration(connection, user_id, edit.aspiration_id)
    if edit.deadline is not None and edit.deadline < goal.start_date:
        raise NotAllowed("A deadline can't be before the start date.")
    updated = queries.update_goal(
        goals.UpdateGoalParams(
            id=goal_id,
            user_id=user_id,
            label=edit.label,
            measurable_line=edit.measurable_line,
            baseline=edit.baseline,
            aspiration_id=edit.aspiration_id,
            deadline=edit.deadline,
        )
    )
    assert updated is not None
    return updated, latest_target(connection, user_id, goal_id)


def lock_user(connection: Connection, user_id: UUID) -> users.GetUserRow:
    """Writes to a user's goals run one at a time."""
    queries = users.Querier(connection)
    queries.lock_user(id=user_id)
    owner = queries.get_user(id=user_id)
    assert owner is not None
    return owner


def check_aspiration(connection: Connection, user_id: UUID, aspiration_id: UUID) -> None:
    """A goal goes under one of the owner's active aspirations."""
    aspiration = aspirations.Querier(connection).get_aspiration(id=aspiration_id, user_id=user_id)
    if aspiration is None:
        raise NotFound
    if aspiration.status != "active":
        raise NotAllowed("A goal can't be put under a retired aspiration.")


def latest_target(
    connection: Connection, user_id: UUID, goal_id: UUID
) -> models.WeeklyTarget | None:
    return weekly_targets.Querier(connection).latest_weekly_target(goal_id=goal_id, user_id=user_id)


def set_target(
    connection: Connection, user_id: UUID, goal_id: UUID, target: WeeklyTargetInput, week: date
) -> models.WeeklyTarget:
    """Sets the goal's target from the week given, replacing one set earlier that week."""
    changed = weekly_targets.Querier(connection).set_weekly_target(
        weekly_targets.SetWeeklyTargetParams(
            id=uuid4(),
            user_id=user_id,
            goal_id=goal_id,
            kind=target.kind,
            sessions=target.sessions,
            amount=target.stored_amount(),
            unit=target.unit,
            effective_from=week,
        )
    )
    latest = changed or latest_target(connection, user_id, goal_id)
    assert latest is not None
    return latest
