"""The user lock, which every write that numbers or plans a user's rows takes first."""

from uuid import UUID

from sqlalchemy import Connection

from app.db import users


def lock_user(connection: Connection, user_id: UUID) -> users.GetUserRow:
    """Waits for the user's row, so two writes arriving together (as an offline queue can
    send them) run one after the other. Returns the user, read under the lock."""
    queries = users.Querier(connection)
    queries.lock_user(id=user_id)
    owner = queries.get_user(id=user_id)
    assert owner is not None
    return owner
