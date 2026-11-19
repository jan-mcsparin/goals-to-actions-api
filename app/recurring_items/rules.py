"""Recurring items: the writes that need more than one query. Each runs inside the caller's
transaction."""

from uuid import UUID

from sqlalchemy import Connection

from app.db import aspirations, goals, models, recurring_items
from app.errors import NotAllowed, NotFound
from app.recurring_items.models import NewRecurringItem, RecurringItemEdit, StoredSchedule
from app.users import lock_user


def create(
    connection: Connection, user_id: UUID, item_id: UUID, new: NewRecurringItem
) -> models.RecurringItem:
    """Adds the item, turned on. Sent again, it returns the item as it is."""
    lock_user(connection, user_id)
    queries = recurring_items.Querier(connection)
    existing = queries.get_recurring_item(id=item_id, user_id=user_id)
    if existing:
        return existing
    if new.aspiration_id is not None:
        check_aspiration(connection, user_id, new.aspiration_id)
    if new.from_goal_id is not None:
        if goals.Querier(connection).get_goal(id=new.from_goal_id, user_id=user_id) is None:
            raise NotFound
    stored = StoredSchedule.of(new.schedule)
    created = queries.create_recurring_item(
        recurring_items.CreateRecurringItemParams(
            id=item_id,
            user_id=user_id,
            name=new.name,
            aspiration_id=new.aspiration_id,
            from_goal_id=new.from_goal_id,
            schedule_kind=stored.schedule_kind,
            weekday=stored.weekday,
            day_of_month=stored.day_of_month,
            times=stored.times,
            period=stored.period,
            starts_on=new.starts_on,
        )
    )
    if created is None:
        raise NotAllowed("That id is already in use.")
    return created


def update(
    connection: Connection, user_id: UUID, item_id: UUID, edit: RecurringItemEdit
) -> models.RecurringItem:
    """Changes the name, the aspiration, the schedule and the start. An item can stay under
    its retired aspiration, but can't be moved under one."""
    lock_user(connection, user_id)
    queries = recurring_items.Querier(connection)
    item = queries.get_recurring_item(id=item_id, user_id=user_id)
    if item is None:
        raise NotFound
    if edit.aspiration_id is not None and edit.aspiration_id != item.aspiration_id:
        check_aspiration(connection, user_id, edit.aspiration_id)
    stored = StoredSchedule.of(edit.schedule)
    updated = queries.update_recurring_item(
        recurring_items.UpdateRecurringItemParams(
            id=item_id,
            user_id=user_id,
            name=edit.name,
            aspiration_id=edit.aspiration_id,
            schedule_kind=stored.schedule_kind,
            weekday=stored.weekday,
            day_of_month=stored.day_of_month,
            times=stored.times,
            period=stored.period,
            starts_on=edit.starts_on,
        )
    )
    assert updated is not None
    return updated


def check_aspiration(connection: Connection, user_id: UUID, aspiration_id: UUID) -> None:
    """An item goes under one of the owner's active aspirations."""
    aspiration = aspirations.Querier(connection).get_aspiration(id=aspiration_id, user_id=user_id)
    if aspiration is None:
        raise NotFound
    if aspiration.status != "active":
        raise NotAllowed("A recurring item can't be put under a retired aspiration.")
