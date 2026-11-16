"""Aspirations: the writes that keep active positions numbered 1 to n. Each runs inside the
caller's transaction."""

from datetime import date
from uuid import UUID

from sqlalchemy import Connection

from app.db import aspirations, models, users
from app.errors import NotAllowed, NotFound


def create(
    connection: Connection, user_id: UUID, aspiration_id: UUID, name: str, why: str | None
) -> models.Aspiration:
    """Adds the aspiration last in priority. Sent again, it returns the row as it is."""
    users.Querier(connection).lock_user(id=user_id)
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
    users.Querier(connection).lock_user(id=user_id)
    queries = aspirations.Querier(connection)
    active = {row.id for row in queries.list_aspirations(user_id=user_id) if row.status == "active"}
    if len(ids) != len(active) or set(ids) != active:
        raise NotAllowed("The order must list every active aspiration once.")
    queries.set_aspiration_positions(user_id=user_id, ids=ids)
    return list(queries.list_aspirations(user_id=user_id))


def retire(
    connection: Connection, user_id: UUID, aspiration_id: UUID, today: date
) -> models.Aspiration:
    """Retires the aspiration and moves up the ones below it. Sent again, it changes nothing."""
    users.Querier(connection).lock_user(id=user_id)
    queries = aspirations.Querier(connection)
    existing = queries.get_aspiration(id=aspiration_id, user_id=user_id)
    if existing is None:
        raise NotFound
    if existing.position is None:
        return existing
    retired = queries.retire_aspiration(id=aspiration_id, user_id=user_id, retired_on=today)
    queries.close_aspiration_gap(user_id=user_id, position=existing.position)
    return retired or existing


def bring_back(connection: Connection, user_id: UUID, aspiration_id: UUID) -> models.Aspiration:
    """Makes a retired aspiration active again, last in priority. Sent again, it changes
    nothing."""
    users.Querier(connection).lock_user(id=user_id)
    queries = aspirations.Querier(connection)
    existing = queries.get_aspiration(id=aspiration_id, user_id=user_id)
    if existing is None:
        raise NotFound
    return queries.bring_back_aspiration(id=aspiration_id, user_id=user_id) or existing
