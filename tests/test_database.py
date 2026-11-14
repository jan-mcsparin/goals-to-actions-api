import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app.config import FIXED_USER_ID
from app.database import Database, current_user_id


def test_the_current_user_is_the_fixed_user_until_sign_in() -> None:
    assert current_user_id() == FIXED_USER_ID


def test_a_read_connection_refuses_writes(test_engine: Engine) -> None:
    database = Database(test_engine)

    with pytest.raises(DBAPIError, match="read-only transaction"):
        with database.read() as connection:
            connection.execute(
                text("update users set time_zone = 'UTC' where id = :id"), {"id": FIXED_USER_ID}
            )
