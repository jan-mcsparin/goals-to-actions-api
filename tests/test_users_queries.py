from datetime import date
from uuid import uuid4

from app.config import FIXED_USER_ID
from app.database import Database
from app.db.users import Querier


def test_the_fixed_user_exists_with_normal_intensity(database: Database) -> None:
    with database.read() as connection:
        user = Querier(connection).get_user(id=FIXED_USER_ID)

    assert user is not None
    assert user.id == FIXED_USER_ID
    assert user.intensity == "normal"
    assert user.time_zone is None
    assert user.planned_through_week is None


def test_set_intensity_is_read_back(database: Database) -> None:
    with database.transaction(FIXED_USER_ID, "set intensity") as connection:
        Querier(connection).set_intensity(id=FIXED_USER_ID, intensity="easing_off")

    with database.read() as connection:
        user = Querier(connection).get_user(id=FIXED_USER_ID)

    assert user is not None
    assert user.intensity == "easing_off"


def test_set_time_zone_is_read_back(database: Database) -> None:
    with database.transaction(FIXED_USER_ID, "set time zone") as connection:
        Querier(connection).set_time_zone(id=FIXED_USER_ID, time_zone="America/Denver")

    with database.read() as connection:
        user = Querier(connection).get_user(id=FIXED_USER_ID)

    assert user is not None
    assert user.time_zone == "America/Denver"


def test_set_planned_through_week_is_read_back(database: Database) -> None:
    monday = date(2026, 11, 9)

    with database.transaction(FIXED_USER_ID, "plan week") as connection:
        Querier(connection).set_planned_through_week(id=FIXED_USER_ID, planned_through_week=monday)

    with database.read() as connection:
        user = Querier(connection).get_user(id=FIXED_USER_ID)

    assert user is not None
    assert user.planned_through_week == monday


def test_a_nullable_value_can_be_set_back_to_empty(database: Database) -> None:
    with database.transaction(FIXED_USER_ID, "set time zone") as connection:
        Querier(connection).set_time_zone(id=FIXED_USER_ID, time_zone="Europe/London")
    with database.transaction(FIXED_USER_ID, "clear time zone") as connection:
        Querier(connection).set_time_zone(id=FIXED_USER_ID, time_zone=None)

    with database.read() as connection:
        user = Querier(connection).get_user(id=FIXED_USER_ID)

    assert user is not None
    assert user.time_zone is None


def test_an_unknown_user_is_none(database: Database) -> None:
    with database.read() as connection:
        assert Querier(connection).get_user(id=uuid4()) is None
