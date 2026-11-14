from uuid import uuid4

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from app.config import FIXED_USER_ID
from app.database import Database


def test_updated_at_moves_on_update_and_created_at_does_not(
    database: Database, connection: Connection
) -> None:
    user_id = uuid4()
    with database.transaction(FIXED_USER_ID, "add user") as tx:
        tx.execute(text("insert into users (id) values (:id)"), {"id": user_id})
    times = text("select created_at, updated_at from users where id = :id")
    before = connection.execute(times, {"id": user_id}).one()

    with database.transaction(FIXED_USER_ID, "set time zone") as tx:
        tx.execute(text("update users set time_zone = 'UTC' where id = :id"), {"id": user_id})

    after = connection.execute(times, {"id": user_id}).one()
    assert after.updated_at > before.updated_at
    assert after.created_at == before.created_at


def test_an_intensity_outside_the_three_is_refused(database: Database) -> None:
    with pytest.raises(IntegrityError, match="users_intensity_check"):
        with database.transaction(FIXED_USER_ID, "set intensity") as tx:
            tx.execute(
                text("update users set intensity = 'flat_out' where id = :id"),
                {"id": FIXED_USER_ID},
            )
