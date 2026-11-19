"""Aspirations: the writes that keep active positions numbered 1 to n. Each runs inside the
caller's transaction."""

from datetime import date
from uuid import UUID

from sqlalchemy import Connection

from app.db import aspirations, goals, models, recurring_items
from app.errors import NotAllowed, NotFound
from app.tasks import rules as task_rules
from app.users import lock_user
from app.weeks import open_weeks


def create(
    connection: Connection, user_id: UUID, aspiration_id: UUID, name: str, why: str | None
) -> models.Aspiration:
    """Adds the aspiration last in priority. Sent again, it returns the row as it is."""
    lock_user(connection, user_id)
    queries = aspirations.Querier(connection)
    existing = queries.get_aspiration(id=aspiration_id, user_id=user_id)
    if existing:
        return existing
    created = queries.create_aspiration(id=aspiration_id, user_id=user_id, name=name, why=why)
    if created is None:
        raise NotAllowed("That id is already in use.")
    return created


def reorder(connection: Connection, user_id: UUID, ids: list[UUID]) -> list[models.Aspiration]:
    """Puts the active aspirations in the order given, which must name each of them once."""
    lock_user(connection, user_id)
    queries = aspirations.Querier(connection)
    active = {row.id for row in queries.list_aspirations(user_id=user_id) if row.status == "active"}
    if len(ids) != len(active) or set(ids) != active:
        raise NotAllowed("The order must list every active aspiration once.")
    queries.set_aspiration_positions(user_id=user_id, ids=ids)
    return list(queries.list_aspirations(user_id=user_id))


def retire(
    connection: Connection, user_id: UUID, aspiration_id: UUID, today: date, pause_its_work: bool
) -> models.Aspiration:
    """Retires the aspiration and moves up the ones below it. Pausing its work pauses its
    active goals and turns its recurring items off, setting their open tasks aside; keeping
    its work going makes its items maintenance. Sent again, it changes nothing."""
    owner = lock_user(connection, user_id)
    queries = aspirations.Querier(connection)
    existing = queries.get_aspiration(id=aspiration_id, user_id=user_id)
    if existing is None:
        raise NotFound
    if existing.position is None:  # already retired
        return existing
    retired = queries.retire_aspiration(id=aspiration_id, user_id=user_id, retired_on=today)
    queries.close_aspiration_gap(user_id=user_id, position=existing.position)
    if pause_its_work:
        current = open_weeks(today, owner.planned_through_week, owner.closed_through_week).current
        pause_work(connection, user_id, aspiration_id, current)
    else:
        recurring_items.Querier(connection).clear_aspiration_items(
            aspiration_id=aspiration_id, user_id=user_id
        )
    return retired or existing


def pause_work(connection: Connection, user_id: UUID, aspiration_id: UUID, current: date) -> None:
    """Pauses the aspiration's active goals and turns its items off, and sets their open
    tasks aside."""
    paused = list(
        goals.Querier(connection).pause_aspiration_goals(
            aspiration_id=aspiration_id, user_id=user_id
        )
    )
    turned_off = list(
        recurring_items.Querier(connection).turn_off_aspiration_items(
            aspiration_id=aspiration_id, user_id=user_id
        )
    )
    for goal_id in paused:
        rows = task_rules.goal_task_weeks(connection, user_id, goal_id)
        task_rules.set_aside(connection, user_id, rows, current)
    for item_id in turned_off:
        rows = task_rules.item_task_weeks(connection, user_id, item_id)
        task_rules.set_aside(connection, user_id, rows, current)


def bring_back(connection: Connection, user_id: UUID, aspiration_id: UUID) -> models.Aspiration:
    """Makes a retired aspiration active again, last in priority. Sent again, it changes
    nothing."""
    lock_user(connection, user_id)
    queries = aspirations.Querier(connection)
    existing = queries.get_aspiration(id=aspiration_id, user_id=user_id)
    if existing is None:
        raise NotFound
    return queries.bring_back_aspiration(id=aspiration_id, user_id=user_id) or existing
