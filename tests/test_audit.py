from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, Engine, create_engine, text

from app.config import FIXED_USER_ID
from app.database import Database
from tests.conftest import TEST_DATABASE_URL


def audit_rows(connection: Connection, row_id: UUID) -> list[Any]:
    return list(
        connection.execute(
            text(
                "select operation, old_row, new_row, user_id, action from audit_log "
                "where row_id = :row_id order by id"
            ),
            {"row_id": row_id},
        )
    )


def test_an_insert_writes_one_audit_row_with_the_new_row(
    database: Database, connection: Connection
) -> None:
    user_id = uuid4()

    with database.transaction(FIXED_USER_ID, "add user") as tx:
        tx.execute(text("insert into users (id) values (:id)"), {"id": user_id})

    [row] = audit_rows(connection, user_id)
    assert row.operation == "insert"
    assert row.old_row is None
    assert row.new_row["id"] == str(user_id)
    assert row.new_row["intensity"] == "normal"


def test_an_update_writes_one_audit_row_with_before_and_after(
    database: Database, connection: Connection
) -> None:
    user_id = uuid4()
    with database.transaction(FIXED_USER_ID, "add user") as tx:
        tx.execute(text("insert into users (id) values (:id)"), {"id": user_id})

    with database.transaction(FIXED_USER_ID, "set intensity") as tx:
        tx.execute(
            text("update users set intensity = 'going_hard' where id = :id"), {"id": user_id}
        )

    [_, row] = audit_rows(connection, user_id)
    assert row.operation == "update"
    assert row.old_row["intensity"] == "normal"
    assert row.new_row["intensity"] == "going_hard"


def test_a_delete_writes_one_audit_row_with_the_old_row(
    database: Database, connection: Connection
) -> None:
    user_id = uuid4()
    with database.transaction(FIXED_USER_ID, "add user") as tx:
        tx.execute(text("insert into users (id) values (:id)"), {"id": user_id})

    with database.transaction(FIXED_USER_ID, "remove user") as tx:
        tx.execute(text("delete from users where id = :id"), {"id": user_id})

    [_, row] = audit_rows(connection, user_id)
    assert row.operation == "delete"
    assert row.old_row["id"] == str(user_id)
    assert row.new_row is None


def test_a_write_inside_transaction_carries_its_user_and_action(
    database: Database, connection: Connection
) -> None:
    with database.transaction(FIXED_USER_ID, "set time zone") as tx:
        tx.execute(
            text("update users set time_zone = 'America/Denver' where id = :id"),
            {"id": FIXED_USER_ID},
        )

    row = audit_rows(connection, FIXED_USER_ID)[-1]
    assert row.user_id == FIXED_USER_ID
    assert row.action == "set time zone"


def test_a_write_outside_transaction_has_no_user_or_action(connection: Connection) -> None:
    before = audit_rows(connection, FIXED_USER_ID)

    connection.execute(
        text("update users set time_zone = 'UTC' where id = :id"), {"id": FIXED_USER_ID}
    )

    after = audit_rows(connection, FIXED_USER_ID)
    assert len(after) == len(before) + 1
    row = after[-1]
    assert row.operation == "update"
    assert row.user_id is None
    assert row.action is None


def test_the_audit_log_itself_is_not_audited(connection: Connection) -> None:
    count = text("select count(*) from audit_log")
    before = connection.execute(count).scalar_one()

    connection.execute(text("delete from audit_log where id = (select min(id) from audit_log)"))

    assert connection.execute(count).scalar_one() == before - 1


@pytest.fixture
def one_connection_engine(test_engine: Engine) -> Iterator[Engine]:
    """An engine whose pool holds exactly one connection, so every transaction reuses it."""
    engine = create_engine(TEST_DATABASE_URL, pool_size=1, max_overflow=0)
    yield engine
    engine.dispose()


def test_the_next_transaction_on_a_pooled_connection_does_not_inherit_the_user(
    one_connection_engine: Engine,
) -> None:
    # The one test that commits: savepoints can't show what's left on a connection after a
    # real commit. It puts back what it changed.
    engine = one_connection_engine
    with engine.connect() as connection:
        last_id = connection.execute(text("select coalesce(max(id), 0) from audit_log")).scalar()
        time_zone = connection.execute(
            text("select time_zone from users where id = :id"), {"id": FIXED_USER_ID}
        ).scalar()

    try:
        with Database(engine).transaction(FIXED_USER_ID, "set time zone") as tx:
            tx.execute(
                text("update users set time_zone = 'Asia/Tokyo' where id = :id"),
                {"id": FIXED_USER_ID},
            )
        with engine.begin() as connection:
            connection.execute(
                text("update users set time_zone = :time_zone where id = :id"),
                {"time_zone": time_zone, "id": FIXED_USER_ID},
            )

        with engine.connect() as connection:
            first, second = connection.execute(
                text("select user_id, action from audit_log where id > :last_id order by id"),
                {"last_id": last_id},
            )
        assert (first.user_id, first.action) == (FIXED_USER_ID, "set time zone")
        assert (second.user_id, second.action) == (None, None)
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("update users set time_zone = :time_zone where id = :id"),
                {"time_zone": time_zone, "id": FIXED_USER_ID},
            )
            connection.execute(text("delete from audit_log where id > :id"), {"id": last_id})
