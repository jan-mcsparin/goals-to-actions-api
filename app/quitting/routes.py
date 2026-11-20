from datetime import date
from uuid import UUID

from fastapi import APIRouter

from app.dependencies import CurrentDatabase, CurrentUserId
from app.quitting import rules
from app.quitting.models import QuitAnswer, QuitDay, UrgeRating
from app.quitting.record import quit_day
from app.schemas import NOT_ALLOWED, NOT_FOUND
from app.turnover.dependencies import Today

router = APIRouter(prefix="/goals", tags=["quitting"])


@router.put("/{goal_id}/quit-days/{day}", responses=NOT_FOUND | NOT_ALLOWED)
def answer_quit_day(
    goal_id: UUID,
    day: date,
    body: QuitAnswer,
    database: CurrentDatabase,
    user_id: CurrentUserId,
    today: Today,
) -> QuitDay:
    """Yes or no for a day. Answering again replaces it."""
    with database.transaction(user_id, "answer quit day") as connection:
        rules.answer(connection, user_id, goal_id, day, body.held, today)
        return quit_day(connection, user_id, goal_id, day)


@router.post("/{goal_id}/quit-days/{day}/clear", responses=NOT_FOUND | NOT_ALLOWED)
def clear_quit_day(
    goal_id: UUID, day: date, database: CurrentDatabase, user_id: CurrentUserId, today: Today
) -> QuitDay:
    """Back to unknown."""
    with database.transaction(user_id, "clear quit day") as connection:
        rules.clear(connection, user_id, goal_id, day, today)
        return quit_day(connection, user_id, goal_id, day)


@router.put("/{goal_id}/urges/{day}", responses=NOT_FOUND | NOT_ALLOWED)
def rate_urge(
    goal_id: UUID,
    day: date,
    body: UrgeRating,
    database: CurrentDatabase,
    user_id: CurrentUserId,
    today: Today,
) -> QuitDay:
    """How strong the urge was that day. Rating again replaces it. Never asked for."""
    with database.transaction(user_id, "rate urge") as connection:
        rules.rate_urge(connection, user_id, goal_id, day, body.level, today)
        return quit_day(connection, user_id, goal_id, day)


@router.post("/{goal_id}/urges/{day}/clear", responses=NOT_FOUND | NOT_ALLOWED)
def clear_urge_rating(
    goal_id: UUID, day: date, database: CurrentDatabase, user_id: CurrentUserId, today: Today
) -> QuitDay:
    with database.transaction(user_id, "clear urge rating") as connection:
        rules.clear_urge(connection, user_id, goal_id, day, today)
        return quit_day(connection, user_id, goal_id, day)
