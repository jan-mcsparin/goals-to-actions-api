from fastapi import APIRouter

from app.dependencies import CurrentDatabase, CurrentUserId
from app.schemas import NOT_ALLOWED
from app.tasks.models import Week
from app.tasks.routes import Monday
from app.tasks.week import week_read
from app.turnover import rules
from app.turnover.dependencies import Today

router = APIRouter(tags=["weeks"])


@router.post("/weeks/{week}/wrap-up", responses=NOT_ALLOWED)
def wrap_up_week(
    week: Monday, database: CurrentDatabase, user_id: CurrentUserId, today: Today
) -> Week:
    """Closes the current week early, once next week is open, and returns the new current
    week. Sent again, it returns the current week as it is."""
    with database.transaction(user_id, "wrap up week") as connection:
        current = rules.wrap_up(connection, user_id, week, today)
        return week_read(connection, user_id, current, today)
