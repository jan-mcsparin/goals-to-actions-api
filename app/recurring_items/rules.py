"""Recurring items: the writes that need more than one query. Each runs inside the caller's
transaction."""

from datetime import date
from uuid import UUID

from sqlalchemy import Connection

from app.db import aspirations, goals, models, recurring_items
from app.errors import NotAllowed, NotFound
from app.recurring_items.models import NewRecurringItem, RecurringItemEdit, StoredSchedule
from app.tasks import rules as task_rules
from app.turnover.rules import fill_item
from app.users import lock_user
from app.weeks import open_weeks


def create(
    connection: Connection, user_id: UUID, item_id: UUID, new: NewRecurringItem, today: date
) -> models.RecurringItem:
    """Adds the item, turned on, with the tasks each open week is due. Sent again, it returns
    the item as it is."""
    owner = lock_user(connection, user_id)
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
    weeks = open_weeks(today, owner.planned_through_week, owner.closed_through_week)
    fill_item(connection, user_id, item_id, weeks, today)
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


def turn(
    connection: Connection, user_id: UUID, item_id: UUID, today: date, *, on: bool
) -> models.RecurringItem:
    """Off sets the item's open tasks aside in every open week; on returns them, the way a
    paused goal's are. Coming on under a retired aspiration, it carries on as maintenance.
    Sent again, it changes nothing."""
    owner = lock_user(connection, user_id)
    queries = recurring_items.Querier(connection)
    item = queries.get_recurring_item(id=item_id, user_id=user_id)
    if item is None:
        raise NotFound
    if item.active == on:
        return item
    aspiration_id = item.aspiration_id
    if (
        on
        and aspiration_id is not None
        and not aspiration_is_active(connection, user_id, aspiration_id)
    ):
        aspiration_id = None
    updated = queries.set_recurring_item_active(
        id=item_id, user_id=user_id, active=on, aspiration_id=aspiration_id
    )
    assert updated is not None
    current = open_weeks(today, owner.planned_through_week, owner.closed_through_week).current
    rows = task_rules.item_task_weeks(connection, user_id, item_id)
    if on:
        task_rules.bring_back(connection, user_id, rows, current)
        weeks = open_weeks(today, owner.planned_through_week, owner.closed_through_week)
        fill_item(connection, user_id, item_id, weeks, today)
    else:
        task_rules.set_aside(connection, user_id, rows, current)
    return updated


def aspiration_is_active(connection: Connection, user_id: UUID, aspiration_id: UUID) -> bool:
    aspiration = aspirations.Querier(connection).get_aspiration(id=aspiration_id, user_id=user_id)
    return aspiration is not None and aspiration.status == "active"


def check_aspiration(connection: Connection, user_id: UUID, aspiration_id: UUID) -> None:
    """An item goes under one of the owner's active aspirations."""
    aspiration = aspirations.Querier(connection).get_aspiration(id=aspiration_id, user_id=user_id)
    if aspiration is None:
        raise NotFound
    if aspiration.status != "active":
        raise NotAllowed("A recurring item can't be put under a retired aspiration.")
