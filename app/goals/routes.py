from uuid import UUID

from fastapi import APIRouter

from app.db import goals, weekly_targets
from app.dependencies import CurrentDatabase, CurrentUserId
from app.errors import NotFound
from app.goals import rules
from app.goals.models import Goal, GoalEdit, GoalList, NewGoal
from app.schemas import NOT_ALLOWED, NOT_FOUND
from app.time_zone import Today

router = APIRouter(prefix="/goals", tags=["goals"])


@router.get("")
def list_goals(database: CurrentDatabase, user_id: CurrentUserId, today: Today) -> GoalList:
    with database.read() as connection:
        rows = list(goals.Querier(connection).list_goals(user_id=user_id))
        targets = {
            target.goal_id: target
            for target in weekly_targets.Querier(connection).latest_weekly_targets(user_id=user_id)
        }
    return GoalList(goals=[Goal.from_row(row, targets.get(row.id), today) for row in rows])


@router.get("/{goal_id}", responses=NOT_FOUND)
def get_goal(
    goal_id: UUID, database: CurrentDatabase, user_id: CurrentUserId, today: Today
) -> Goal:
    with database.read() as connection:
        row = goals.Querier(connection).get_goal(id=goal_id, user_id=user_id)
        if row is None:
            raise NotFound
        target = rules.latest_target(connection, user_id, goal_id)
    return Goal.from_row(row, target, today)


@router.put("/{goal_id}", responses=NOT_FOUND | NOT_ALLOWED)
def create_goal(
    goal_id: UUID, body: NewGoal, database: CurrentDatabase, user_id: CurrentUserId, today: Today
) -> Goal:
    with database.transaction(user_id, "create goal") as connection:
        row, target = rules.create(connection, user_id, goal_id, body, today)
    return Goal.from_row(row, target, today)


@router.patch("/{goal_id}", responses=NOT_FOUND | NOT_ALLOWED)
def update_goal(
    goal_id: UUID, body: GoalEdit, database: CurrentDatabase, user_id: CurrentUserId, today: Today
) -> Goal:
    with database.transaction(user_id, "update goal") as connection:
        row, target = rules.update(connection, user_id, goal_id, body)
    return Goal.from_row(row, target, today)
