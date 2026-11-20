from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.config import FIXED_USER_ID
from app.database import Database

ADD_ACTIVE = text(
    "insert into aspirations (id, user_id, name, position) values (:id, :user_id, :name, :position)"
)


def add_active(database: Database, position: int, name: str = "Be fit") -> UUID:
    aspiration_id = uuid4()
    with database.transaction(FIXED_USER_ID, "create aspiration") as tx:
        tx.execute(
            ADD_ACTIVE,
            {"id": aspiration_id, "user_id": FIXED_USER_ID, "name": name, "position": position},
        )
    return aspiration_id


def test_two_active_aspirations_cannot_share_a_position(database: Database) -> None:
    add_active(database, 1)

    with pytest.raises(IntegrityError, match="aspirations_position_unique"):
        add_active(database, 1)


def test_a_deleted_aspiration_gives_up_its_position(database: Database) -> None:
    deleted = add_active(database, 1)
    with database.transaction(FIXED_USER_ID, "delete aspiration") as tx:
        tx.execute(
            text("update aspirations set deleted_at = now() where id = :id"), {"id": deleted}
        )

    add_active(database, 1)


def test_one_statement_can_swap_two_positions(database: Database) -> None:
    first = add_active(database, 1)
    second = add_active(database, 2)

    with database.transaction(FIXED_USER_ID, "reorder aspirations") as tx:
        tx.execute(text("update aspirations set position = 3 - position"))
        rows = tx.execute(text("select id, position from aspirations")).all()

    assert {row.id: row.position for row in rows} == {first: 2, second: 1}


def test_another_owner_can_use_the_same_position(database: Database) -> None:
    other_user = uuid4()
    add_active(database, 1)

    with database.transaction(FIXED_USER_ID, "add user") as tx:
        tx.execute(text("insert into users (id) values (:id)"), {"id": other_user})
        tx.execute(
            ADD_ACTIVE, {"id": uuid4(), "user_id": other_user, "name": "Be kind", "position": 1}
        )


@pytest.mark.parametrize(
    "columns",
    [
        "status = 'active', position = null",
        "status = 'active', position = 0",
        "status = 'active', retired_on = '2026-11-10'",
        "status = 'retired', position = null, retired_on = null",
        "status = 'retired', position = 1, retired_on = '2026-11-10'",
    ],
)
def test_status_position_and_retired_day_must_agree(database: Database, columns: str) -> None:
    aspiration_id = add_active(database, 1)

    with pytest.raises(IntegrityError, match="aspirations_status_agrees"):
        with database.transaction(FIXED_USER_ID, "retire aspiration") as tx:
            tx.execute(
                text(f"update aspirations set {columns} where id = :id"), {"id": aspiration_id}
            )


def test_a_retired_aspiration_has_a_day_and_no_position(database: Database) -> None:
    aspiration_id = add_active(database, 1)

    with database.transaction(FIXED_USER_ID, "retire aspiration") as tx:
        tx.execute(
            text(
                "update aspirations set status = 'retired', position = null, "
                "retired_on = '2026-11-10' where id = :id"
            ),
            {"id": aspiration_id},
        )


def test_a_blank_name_is_refused(database: Database) -> None:
    with pytest.raises(IntegrityError, match="aspirations_name_not_blank"):
        add_active(database, 1, name="   ")


def test_an_unknown_status_is_refused(database: Database) -> None:
    aspiration_id = add_active(database, 1)

    with pytest.raises(IntegrityError, match="aspirations_status_agrees"):
        with database.transaction(FIXED_USER_ID, "retire aspiration") as tx:
            tx.execute(
                text("update aspirations set status = 'paused' where id = :id"),
                {"id": aspiration_id},
            )


def test_an_aspiration_needs_an_owner_who_exists(database: Database) -> None:
    with pytest.raises(IntegrityError, match="aspirations_user_id_fkey"):
        with database.transaction(FIXED_USER_ID, "create aspiration") as tx:
            tx.execute(
                ADD_ACTIVE, {"id": uuid4(), "user_id": uuid4(), "name": "Be fit", "position": 1}
            )
