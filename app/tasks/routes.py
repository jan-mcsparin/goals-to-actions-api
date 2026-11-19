from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.exceptions import RequestValidationError

from app.dependencies import CurrentDatabase, CurrentUserId
from app.schemas import NOT_ALLOWED, NOT_FOUND
from app.tasks import rules
from app.tasks.models import CheckOff, NewTask, Task, TaskEdit, Week
from app.tasks.week import task_view, week_read
from app.time_zone import Today

router = APIRouter(tags=["tasks"])


def monday(week: date) -> date:
    """A week is named by its Monday."""
    if week.weekday() != 0:
        raise RequestValidationError(
            [
                {
                    "type": "monday",
                    "loc": ("path", "week"),
                    "msg": "A week is named by the date of its Monday.",
                    "input": week.isoformat(),
                }
            ]
        )
    return week


Monday = Annotated[date, Depends(monday)]


@router.get("/weeks/{week}")
def get_week(week: Monday, database: CurrentDatabase, user_id: CurrentUserId, today: Today) -> Week:
    with database.read() as connection:
        return week_read(connection, user_id, week, today)


@router.put("/tasks/{task_id}", responses=NOT_FOUND | NOT_ALLOWED)
def add_task(
    task_id: UUID, body: NewTask, database: CurrentDatabase, user_id: CurrentUserId, today: Today
) -> Task:
    with database.transaction(user_id, "add task") as connection:
        rules.add(connection, user_id, task_id, body, today)
        return task_view(connection, user_id, task_id)


@router.patch("/tasks/{task_id}", responses=NOT_FOUND)
def update_task(
    task_id: UUID, body: TaskEdit, database: CurrentDatabase, user_id: CurrentUserId
) -> Task:
    with database.transaction(user_id, "update task") as connection:
        rules.update(connection, user_id, task_id, body)
        return task_view(connection, user_id, task_id)


@router.post("/tasks/{task_id}/check-off", responses=NOT_FOUND | NOT_ALLOWED)
def check_off_task(
    task_id: UUID, body: CheckOff, database: CurrentDatabase, user_id: CurrentUserId, today: Today
) -> Task:
    with database.transaction(user_id, "check off task") as connection:
        rules.check_off(connection, user_id, task_id, body, today)
        return task_view(connection, user_id, task_id)


@router.post("/tasks/{task_id}/uncheck", responses=NOT_FOUND | NOT_ALLOWED)
def uncheck_task(task_id: UUID, database: CurrentDatabase, user_id: CurrentUserId) -> Task:
    """The task goes back where its row was, on its day or in its bank."""
    with database.transaction(user_id, "uncheck task") as connection:
        rules.uncheck(connection, user_id, task_id)
        return task_view(connection, user_id, task_id)
