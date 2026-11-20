"""Milestones and check-ins: the writes. Each runs inside the caller's transaction and
returns the goal's id, so the route can return the goal's page."""

from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import Connection

from app.db import check_ins, goals, milestones, models
from app.errors import NotAllowed, NotFound
from app.goals import rules as goal_rules
from app.milestones.models import MilestoneEdit, MilestoneOrder, NewCheckIn, NewMilestone
from app.users import lock_user


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


def update(connection: Connection, user_id: UUID, milestone_id: UUID, edit: MilestoneEdit) -> UUID:
    """Changes the line and date. A date moved later pushes the later dated milestones out by
    as much, never past the deadline."""
    lock_user(connection, user_id)
    queries = milestones.Querier(connection)
    milestone = queries.get_milestone(id=milestone_id, user_id=user_id)
    if milestone is None:
        raise NotFound
    goal = goal_with_milestones(connection, user_id, milestone.goal_id)
    check_date(goal, edit.target_date)
    rows = list(queries.list_milestones(goal_id=goal.id, user_id=user_id))
    for later_id, pushed in pushed_dates(rows, milestone, edit.target_date, goal.deadline):
        queries.set_milestone_date(id=later_id, user_id=user_id, target_date=pushed)
    queries.update_milestone(
        id=milestone_id,
        user_id=user_id,
        measurable_line=edit.measurable_line,
        target_date=edit.target_date,
    )
    return goal.id


def reorder(connection: Connection, user_id: UUID, goal_id: UUID, order: MilestoneOrder) -> None:
    """Puts the goal's milestones in the order given, which must name each of them once."""
    lock_user(connection, user_id)
    if goals.Querier(connection).get_goal(id=goal_id, user_id=user_id) is None:
        raise NotFound
    queries = milestones.Querier(connection)
    current = {row.id for row in queries.list_milestones(goal_id=goal_id, user_id=user_id)}
    if len(order.ids) != len(current) or set(order.ids) != current:
        raise NotAllowed("The order must list every milestone of the goal once.")
    queries.set_milestone_positions(ids=order.ids, goal_id=goal_id, user_id=user_id)


def check_in(
    connection: Connection, user_id: UUID, check_in_id: UUID, new: NewCheckIn, today: date
) -> UUID:
    """Keeps the check-in and sets Next's status. A hit on the goal's own line marks the goal
    reached, as "I reached it" does. Sent again, it changes nothing."""
    lock_user(connection, user_id)
    queries = check_ins.Querier(connection)
    existing = queries.get_check_in(id=check_in_id, user_id=user_id)
    if existing:
        if existing.goal_id != new.goal_id:
            raise NotAllowed("That id is already in use.")
        return existing.goal_id
    goal = goal_with_milestones(connection, user_id, new.goal_id)
    if goal.status not in ("active", "paused"):
        raise NotAllowed("Only an active or paused goal can be checked in.")
    rows = milestones.Querier(connection).list_milestones(goal_id=goal.id, user_id=user_id)
    next_up = next((row.id for row in rows if row.status != "hit"), None)
    if new.milestone_id != next_up:
        raise NotAllowed("Only Next can be checked in.")
    outcome = "hit" if new.outcome == "hit" else "not_yet"
    added = queries.add_check_in(
        check_ins.AddCheckInParams(
            id=check_in_id,
            user_id=user_id,
            goal_id=goal.id,
            milestone_id=new.milestone_id,
            outcome=outcome,
            result=new.result,
            checked_in_on=today,
        )
    )
    if added is None:
        raise NotAllowed("That id is already in use.")
    if new.milestone_id is not None:
        milestones.Querier(connection).set_milestone_status(
            id=new.milestone_id, user_id=user_id, status=outcome
        )
    elif outcome == "hit":
        # The same change as "I reached it", so whatever reaching a goal does, this does too.
        goal_rules.change_status(connection, user_id, goal.id, goal_rules.MARK_REACHED, today)
    return goal.id


def keep(connection: Connection, user_id: UUID, milestone_id: UUID) -> UUID:
    """After a "not yet", keeps the milestone as it is and makes it upcoming again. Moving or
    adjusting it is an edit. Sent again, it changes nothing."""
    lock_user(connection, user_id)
    queries = milestones.Querier(connection)
    milestone = queries.get_milestone(id=milestone_id, user_id=user_id)
    if milestone is None:
        raise NotFound
    if milestone.status == "hit":
        raise NotAllowed("A milestone that's hit has nothing to keep.")
    if milestone.status == "not_yet":
        queries.set_milestone_status(id=milestone_id, user_id=user_id, status="upcoming")
    return milestone.goal_id


def delete(connection: Connection, user_id: UUID, milestone_id: UUID) -> UUID:
    """A mistake: the milestone and its check-ins are hidden everywhere, and the ones after it
    move up. Sent again, it changes nothing."""
    lock_user(connection, user_id)
    queries = milestones.Querier(connection)
    milestone = queries.get_milestone(id=milestone_id, user_id=user_id)
    if milestone is None:
        deleted = queries.milestone_deleted(id=milestone_id, user_id=user_id)
        if deleted is None:
            raise NotFound
        return deleted.goal_id
    check_ins.Querier(connection).delete_milestone_check_ins(
        milestone_id=milestone_id, user_id=user_id
    )
    queries.delete_milestone(id=milestone_id, user_id=user_id)
    queries.close_milestone_gap(
        goal_id=milestone.goal_id, user_id=user_id, position=milestone.position
    )
    return milestone.goal_id


def pushed_dates(
    rows: list[models.Milestone],
    moved: models.Milestone,
    new_date: date | None,
    deadline: date | None,
) -> list[tuple[UUID, date]]:
    """The later dated milestones' new dates when `moved` goes from its date to `new_date`.
    Moving earlier, or giving an undated milestone a date, moves nothing."""
    if moved.target_date is None or new_date is None or new_date <= moved.target_date:
        return []
    by = timedelta(days=(new_date - moved.target_date).days)
    pushed = []
    for row in rows:
        if row.position > moved.position and row.target_date is not None:
            new = row.target_date + by
            pushed.append((row.id, min(new, deadline) if deadline else new))
    return pushed


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
