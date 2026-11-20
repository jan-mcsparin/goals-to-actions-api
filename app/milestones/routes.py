from uuid import UUID

from fastapi import APIRouter

from app.dependencies import CurrentDatabase, CurrentUserId
from app.milestones import rules
from app.milestones.models import (
    GoalPage,
    MilestoneEdit,
    MilestoneOrder,
    NewCheckIn,
    NewMilestone,
)
from app.milestones.page import goal_page
from app.schemas import NOT_ALLOWED, NOT_FOUND
from app.turnover.dependencies import Today

router = APIRouter(tags=["milestones"])


@router.put("/milestones/{milestone_id}", responses=NOT_FOUND | NOT_ALLOWED)
def add_milestone(
    milestone_id: UUID,
    body: NewMilestone,
    database: CurrentDatabase,
    user_id: CurrentUserId,
    today: Today,
) -> GoalPage:
    with database.transaction(user_id, "add milestone") as connection:
        goal_id = rules.add(connection, user_id, milestone_id, body)
        return goal_page(connection, user_id, goal_id, today)


@router.patch("/milestones/{milestone_id}", responses=NOT_FOUND | NOT_ALLOWED)
def update_milestone(
    milestone_id: UUID,
    body: MilestoneEdit,
    database: CurrentDatabase,
    user_id: CurrentUserId,
    today: Today,
) -> GoalPage:
    """Also how a "not yet" is moved (a new date) or adjusted (a new line)."""
    with database.transaction(user_id, "update milestone") as connection:
        goal_id = rules.update(connection, user_id, milestone_id, body)
        return goal_page(connection, user_id, goal_id, today)


@router.post("/goals/{goal_id}/milestones/reorder", responses=NOT_FOUND | NOT_ALLOWED)
def reorder_milestones(
    goal_id: UUID,
    body: MilestoneOrder,
    database: CurrentDatabase,
    user_id: CurrentUserId,
    today: Today,
) -> GoalPage:
    with database.transaction(user_id, "reorder milestones") as connection:
        rules.reorder(connection, user_id, goal_id, body)
        return goal_page(connection, user_id, goal_id, today)


@router.put("/check-ins/{check_in_id}", responses=NOT_FOUND | NOT_ALLOWED)
def check_in(
    check_in_id: UUID,
    body: NewCheckIn,
    database: CurrentDatabase,
    user_id: CurrentUserId,
    today: Today,
) -> GoalPage:
    with database.transaction(user_id, "check in") as connection:
        goal_id = rules.check_in(connection, user_id, check_in_id, body, today)
        return goal_page(connection, user_id, goal_id, today)


@router.post("/milestones/{milestone_id}/keep", responses=NOT_FOUND | NOT_ALLOWED)
def keep_milestone(
    milestone_id: UUID, database: CurrentDatabase, user_id: CurrentUserId, today: Today
) -> GoalPage:
    """After a "not yet": keep the date and the line, and make it upcoming again."""
    with database.transaction(user_id, "keep milestone") as connection:
        goal_id = rules.keep(connection, user_id, milestone_id)
        return goal_page(connection, user_id, goal_id, today)


@router.delete("/milestones/{milestone_id}", responses=NOT_FOUND)
def delete_milestone(
    milestone_id: UUID, database: CurrentDatabase, user_id: CurrentUserId, today: Today
) -> GoalPage:
    """For a mistake: the milestone and its check-ins are hidden everywhere, and the ones after
    it move up. Returns the goal's page."""
    with database.transaction(user_id, "delete milestone") as connection:
        goal_id = rules.delete(connection, user_id, milestone_id)
        return goal_page(connection, user_id, goal_id, today)
