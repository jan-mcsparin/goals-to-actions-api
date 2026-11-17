from uuid import UUID

from fastapi import APIRouter

from app.dependencies import CurrentDatabase, CurrentUserId
from app.milestones import rules
from app.milestones.models import GoalPage, MilestoneEdit, NewMilestone
from app.milestones.page import goal_page
from app.schemas import NOT_ALLOWED, NOT_FOUND
from app.time_zone import Today

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
