"""Aspirations: the writes that keep active positions numbered 1 to n. Each runs inside the
caller's transaction."""

from uuid import UUID

from sqlalchemy import Connection

from app.db import aspirations, models, users
from app.errors import NotAllowed


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
