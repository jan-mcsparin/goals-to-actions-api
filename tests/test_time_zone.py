from datetime import UTC, datetime

import pytest
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.config import FIXED_USER_ID
from app.time_zone import now
from tests.test_aspirations import audit_rows

MOMENT = datetime(2026, 11, 18, 19, 0, tzinfo=UTC)


def test_the_moment_is_in_the_time_zone_sent() -> None:
    assert now("America/Denver", MOMENT).hour == 12
    assert now("Pacific/Kiritimati", MOMENT).date().isoformat() == "2026-11-19"


def test_today_differs_across_the_date_line() -> None:
    # 25 hours apart, so never the same day.
    assert now("Pacific/Kiritimati", MOMENT).date() > now("Pacific/Pago_Pago", MOMENT).date()


@pytest.mark.parametrize("name", ["Mars/Olympus_Mons", "", "America", "../etc/passwd", "+07:00"])
def test_an_unknown_time_zone_is_refused(name: str) -> None:
    with pytest.raises(RequestValidationError) as refused:
        now(name, MOMENT)

    [error] = refused.value.errors()
    assert error["loc"] == ("header", "x-time-zone")


def stored_zone(connection: Connection) -> str | None:
    zone: str | None = connection.execute(
        text("select time_zone from users where id = :id"), {"id": FIXED_USER_ID}
    ).scalar_one()
    return zone


def read_week(client: TestClient, zone: str) -> int:
    return client.get("/api/weeks/2026-11-16", headers={"X-Time-Zone": zone}).status_code


def test_the_time_zone_follows_the_phone(client: TestClient, connection: Connection) -> None:
    assert read_week(client, "Asia/Tokyo") == 200
    assert stored_zone(connection) == "Asia/Tokyo"

    assert read_week(client, "America/Denver") == 200
    assert stored_zone(connection) == "America/Denver"


def test_the_same_time_zone_again_writes_nothing(
    client: TestClient, connection: Connection
) -> None:
    read_week(client, "Asia/Tokyo")
    read_week(client, "Asia/Tokyo")

    actions = [row.action for row in audit_rows(connection, FIXED_USER_ID)]
    assert actions.count("set time zone") == 1


def test_a_name_that_isnt_a_zone_is_not_kept(client: TestClient, connection: Connection) -> None:
    read_week(client, "Asia/Tokyo")

    assert read_week(client, "Mars/Olympus_Mons") == 422
    assert stored_zone(connection) == "Asia/Tokyo"


@pytest.mark.parametrize("name", ["america/denver", "ASIA/TOKYO"])
def test_a_zone_name_in_the_wrong_case_is_refused(name: str) -> None:
    # A case-insensitive file system loads these; a Linux host wouldn't.
    with pytest.raises(RequestValidationError):
        now(name, MOMENT)
