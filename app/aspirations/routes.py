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

router = APIRouter(prefix="/aspirations", tags=["aspirations"])


@router.get("")
def list_aspirations(database: CurrentDatabase, user_id: CurrentUserId) -> AspirationList:
    with database.read() as connection:
        rows = list(aspirations.Querier(connection).list_aspirations(user_id=user_id))
    return AspirationList.from_rows(rows)


@router.put("/{aspiration_id}")
def create_aspiration(
    aspiration_id: UUID, body: AspirationInput, database: CurrentDatabase, user_id: CurrentUserId
) -> Aspiration:
    with database.transaction(user_id, "create aspiration") as connection:
        row = rules.create(connection, user_id, aspiration_id, body.name, body.why)
    return Aspiration.from_row(row)


@router.post("/reorder")
def reorder_aspirations(
    body: AspirationOrder, database: CurrentDatabase, user_id: CurrentUserId
) -> AspirationList:
    with database.transaction(user_id, "reorder aspirations") as connection:
        rows = rules.reorder(connection, user_id, body.ids)
    return AspirationList.from_rows(rows)
