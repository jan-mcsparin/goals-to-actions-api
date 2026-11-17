"""Milestones and check-ins: the writes. Each runs inside the caller's transaction and
returns the goal's id, so the route can return the goal's page."""

from datetime import date
from uuid import UUID

from sqlalchemy import Connection

from app.db import goals, milestones, models
from app.errors import NotAllowed, NotFound
from app.goals.rules import lock_user
from app.milestones.models import NewMilestone


def add(connection: Connection, user_id: UUID, milestone_id: UUID, new: NewMilestone) -> UUID:
    """Adds the milestone last. Sent again, it changes nothing."""
    lock_user(connection, user_id)
    queries = milestones.Querier(connection)
    existing = queries.get_milestone(id=milestone_id, user_id=user_id)
    if existing:
        if existing.goal_id != new.goal_id:
            raise NotAllowed("That id is already in use.")
        return existing.goal_id
    goal = goal_with_milestones(connection, user_id, new.goal_id)
    check_date(goal, new.target_date)
    added = queries.add_milestone(
        milestones.AddMilestoneParams(
            id=milestone_id,
            user_id=user_id,
            goal_id=goal.id,
            goal_type=goal.type,
            measurable_line=new.measurable_line,
            target_date=new.target_date,
        )
    )
    if added is None:
        raise NotAllowed("That id is already in use.")
    return goal.id


def goal_with_milestones(connection: Connection, user_id: UUID, goal_id: UUID) -> models.Goal:
    goal = goals.Querier(connection).get_goal(id=goal_id, user_id=user_id)
    if goal is None:
        raise NotFound
    if goal.type not in ("building", "quitting"):
        raise NotAllowed("Only building and quitting goals have milestones.")
    return goal


def check_date(goal: models.Goal, target_date: date | None) -> None:
    """A milestone's date falls between its goal's start and its deadline."""
    if target_date is None:
        return
    if target_date < goal.start_date or (goal.deadline and target_date > goal.deadline):
        raise NotAllowed("A milestone's date falls between its goal's start and deadline.")
