from uuid import UUID

from fastapi import APIRouter, Response, status

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
from app.turnover.dependencies import Today

router = APIRouter(prefix="/recurring-items", tags=["recurring items"])


@router.get("")
def list_recurring_items(database: CurrentDatabase, user_id: CurrentUserId) -> RecurringItemList:
    """Every item, on and off, oldest first. One with no aspiration is in Keep life running."""
    with database.read() as connection:
        rows = recurring_items.Querier(connection).list_recurring_items(user_id=user_id)
        return RecurringItemList(recurring_items=[RecurringItem.from_row(row) for row in rows])


@router.put("/{item_id}", responses=NOT_FOUND | NOT_ALLOWED)
def create_recurring_item(
    item_id: UUID,
    body: NewRecurringItem,
    database: CurrentDatabase,
    user_id: CurrentUserId,
    today: Today,
) -> RecurringItem:
    """Adds the item, with the tasks each open week is due."""
    with database.transaction(user_id, "create recurring item") as connection:
        return RecurringItem.from_row(rules.create(connection, user_id, item_id, body, today))


@router.patch("/{item_id}", responses=NOT_FOUND | NOT_ALLOWED)
def update_recurring_item(
    item_id: UUID, body: RecurringItemEdit, database: CurrentDatabase, user_id: CurrentUserId
) -> RecurringItem:
    with database.transaction(user_id, "update recurring item") as connection:
        return RecurringItem.from_row(rules.update(connection, user_id, item_id, body))


@router.post("/{item_id}/turn-off", responses=NOT_FOUND)
def turn_off_recurring_item(
    item_id: UUID, database: CurrentDatabase, user_id: CurrentUserId, today: Today
) -> RecurringItem:
    """Its open tasks leave the days and the bank in every open week, until it's turned on."""
    with database.transaction(user_id, "turn off recurring item") as connection:
        return RecurringItem.from_row(rules.turn(connection, user_id, item_id, today, on=False))


@router.post("/{item_id}/turn-on", responses=NOT_FOUND)
def turn_on_recurring_item(
    item_id: UUID, database: CurrentDatabase, user_id: CurrentUserId, today: Today
) -> RecurringItem:
    """Its set-aside tasks return to the bank of their week, if that week is still open."""
    with database.transaction(user_id, "turn on recurring item") as connection:
        return RecurringItem.from_row(rules.turn(connection, user_id, item_id, today, on=True))


@router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=NOT_FOUND,
)
def delete_recurring_item(item_id: UUID, database: CurrentDatabase, user_id: CurrentUserId) -> None:
    """For a mistake: the item and its open tasks are hidden everywhere. Its done tasks stay,
    with no item."""
    with database.transaction(user_id, "delete recurring item") as connection:
        rules.delete(connection, user_id, item_id)
