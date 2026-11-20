from uuid import UUID

from sqlalchemy import Connection

from app.db import users


def set_intensity(connection: Connection, user_id: UUID, intensity: str) -> str:
    """Saves the intensity, writing only when it changes, so a repeat leaves no trace."""
    queries = users.Querier(connection)
    owner = queries.get_user(id=user_id)
    assert owner is not None
    if owner.intensity == intensity:
        return owner.intensity
    saved = queries.set_intensity(id=user_id, intensity=intensity)
    assert saved is not None
    return saved.intensity
