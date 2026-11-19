from uuid import UUID

from fastapi import APIRouter

from app.db import recurring_items
from app.dependencies import CurrentDatabase, CurrentUserId
from app.recurring_items import rules
from app.recurring_items.models import (
    NewRecurringItem,
    RecurringItem,
    RecurringItemEdit,
    RecurringItemList,
)
from app.schemas import NOT_ALLOWED, NOT_FOUND

router = APIRouter(prefix="/recurring-items", tags=["recurring items"])


@router.get("")
def list_recurring_items(database: CurrentDatabase, user_id: CurrentUserId) -> RecurringItemList:
    """Every item, on and off, oldest first. One with no aspiration is in Keep life running."""
    with database.read() as connection:
        rows = recurring_items.Querier(connection).list_recurring_items(user_id=user_id)
        return RecurringItemList(recurring_items=[RecurringItem.from_row(row) for row in rows])


@router.put("/{item_id}", responses=NOT_FOUND | NOT_ALLOWED)
def create_recurring_item(
    item_id: UUID, body: NewRecurringItem, database: CurrentDatabase, user_id: CurrentUserId
) -> RecurringItem:
    with database.transaction(user_id, "create recurring item") as connection:
        return RecurringItem.from_row(rules.create(connection, user_id, item_id, body))


@router.patch("/{item_id}", responses=NOT_FOUND | NOT_ALLOWED)
def update_recurring_item(
    item_id: UUID, body: RecurringItemEdit, database: CurrentDatabase, user_id: CurrentUserId
) -> RecurringItem:
    with database.transaction(user_id, "update recurring item") as connection:
        return RecurringItem.from_row(rules.update(connection, user_id, item_id, body))
