from uuid import UUID

from fastapi import APIRouter

from app.aspirations import rules
from app.aspirations.models import (
    Aspiration,
    AspirationInput,
    AspirationList,
    AspirationOrder,
)
from app.db import aspirations
from app.dependencies import CurrentDatabase, CurrentUserId
from app.errors import NotFound
from app.schemas import NOT_ALLOWED, NOT_FOUND
from app.time_zone import Today

router = APIRouter(prefix="/aspirations", tags=["aspirations"])


@router.get("")
def list_aspirations(database: CurrentDatabase, user_id: CurrentUserId) -> AspirationList:
    with database.read() as connection:
        rows = list(aspirations.Querier(connection).list_aspirations(user_id=user_id))
    return AspirationList.from_rows(rows)


@router.put("/{aspiration_id}", responses=NOT_ALLOWED)
def create_aspiration(
    aspiration_id: UUID, body: AspirationInput, database: CurrentDatabase, user_id: CurrentUserId
) -> Aspiration:
    with database.transaction(user_id, "create aspiration") as connection:
        row = rules.create(connection, user_id, aspiration_id, body.name, body.why)
    return Aspiration.from_row(row)


@router.post("/reorder", responses=NOT_ALLOWED)
def reorder_aspirations(
    body: AspirationOrder, database: CurrentDatabase, user_id: CurrentUserId
) -> AspirationList:
    with database.transaction(user_id, "reorder aspirations") as connection:
        rows = rules.reorder(connection, user_id, body.ids)
    return AspirationList.from_rows(rows)


@router.patch("/{aspiration_id}", responses=NOT_FOUND)
def update_aspiration(
    aspiration_id: UUID, body: AspirationInput, database: CurrentDatabase, user_id: CurrentUserId
) -> Aspiration:
    with database.transaction(user_id, "update aspiration") as connection:
        row = aspirations.Querier(connection).update_aspiration(
            id=aspiration_id, user_id=user_id, name=body.name, why=body.why
        )
    if row is None:
        raise NotFound
    return Aspiration.from_row(row)


@router.post("/{aspiration_id}/retire", responses=NOT_FOUND)
def retire_aspiration(
    aspiration_id: UUID, database: CurrentDatabase, user_id: CurrentUserId, today: Today
) -> Aspiration:
    with database.transaction(user_id, "retire aspiration") as connection:
        row = rules.retire(connection, user_id, aspiration_id, today)
    return Aspiration.from_row(row)


@router.post("/{aspiration_id}/bring-back", responses=NOT_FOUND)
def bring_back_aspiration(
    aspiration_id: UUID, database: CurrentDatabase, user_id: CurrentUserId
) -> Aspiration:
    with database.transaction(user_id, "bring back aspiration") as connection:
        row = rules.bring_back(connection, user_id, aspiration_id)
    return Aspiration.from_row(row)
