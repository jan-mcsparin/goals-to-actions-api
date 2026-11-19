"""wrapUpWeek: the person closes the week early, once next week is open."""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from tests.conftest import FixedClock
from tests.test_goals import ZONE

WEEK = date(2026, 11, 16)
NEXT_WEEK = date(2026, 11, 23)
# 7 p.m. in Denver on Sunday 22 Nov 2026.
SUNDAY_EVENING = datetime(2026, 11, 23, 2, 0, tzinfo=UTC)
MONDAY_MORNING = datetime(2026, 11, 23, 15, 0, tzinfo=UTC)


@pytest.fixture
def tasks_client(client: TestClient, fixed_clock: FixedClock) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    fixed_clock.instant = SUNDAY_EVENING
    yield client


def wrap_up(client: TestClient, week: date) -> Any:
    return client.post(f"/api/weeks/{week}/wrap-up")


def add_task(client: TestClient, **body: Any) -> Any:
    response = client.put(f"/api/tasks/{uuid4()}", json={"title": "Call the dentist"} | body)
    assert response.status_code == 200, response.text
    return response.json()


def test_wrapped_up_on_sunday_evening_next_week_becomes_the_current_week(
    tasks_client: TestClient,
) -> None:
    task = add_task(tasks_client, day="2026-11-22")
    assert tasks_client.get(f"/api/weeks/{NEXT_WEEK}").json()["nextWeekOpen"] is True

    response = wrap_up(tasks_client, WEEK)

    assert response.status_code == 200, response.text
    week = response.json()
    assert (week["week"], week["isCurrent"], week["nextWeekOpen"]) == (
        NEXT_WEEK.isoformat(),
        True,
        False,
    )
    assert task["id"] in [row["id"] for row in week["tasks"] if row["plannedDay"] is None]


def test_after_a_wrap_up_next_weeks_tasks_can_be_checked_off(tasks_client: TestClient) -> None:
    add_task(tasks_client, day="2026-11-22")
    tasks_client.get(f"/api/weeks/{NEXT_WEEK}")
    wrap_up(tasks_client, WEEK)
    session = tasks_client.get(f"/api/weeks/{NEXT_WEEK}").json()["tasks"][0]

    done = tasks_client.post(
        f"/api/tasks/{session['id']}/check-off",
        json={"completedAt": "2026-11-23T03:00:00Z", "completedOn": "2026-11-22"},
    )

    assert done.status_code == 200, done.text


def test_a_task_added_to_today_after_a_wrap_up_goes_to_next_weeks_bank(
    tasks_client: TestClient,
) -> None:
    tasks_client.get(f"/api/weeks/{NEXT_WEEK}")
    wrap_up(tasks_client, WEEK)

    task = add_task(tasks_client, day="2026-11-22")

    assert (task["week"], task["plannedDay"]) == (NEXT_WEEK.isoformat(), None)


def test_before_next_week_is_open_it_is_refused(
    tasks_client: TestClient, fixed_clock: FixedClock
) -> None:
    fixed_clock.instant = datetime(2026, 11, 22, 23, 59, tzinfo=UTC)  # 4:59 p.m. Sunday

    assert wrap_up(tasks_client, WEEK).status_code == 409


def test_a_week_after_the_current_one_is_refused(tasks_client: TestClient) -> None:
    tasks_client.get(f"/api/weeks/{NEXT_WEEK}")

    assert wrap_up(tasks_client, NEXT_WEEK).status_code == 409


def test_a_date_that_is_not_a_monday_is_refused(tasks_client: TestClient) -> None:
    assert wrap_up(tasks_client, date(2026, 11, 17)).status_code == 422


def test_sent_twice_the_second_returns_the_current_week_unchanged(
    tasks_client: TestClient, connection: Connection
) -> None:
    add_task(tasks_client, day="2026-11-22")
    tasks_client.get(f"/api/weeks/{NEXT_WEEK}")
    first = wrap_up(tasks_client, WEEK).json()
    rows = connection.execute(text("select count(*) from task_weeks")).scalar_one()

    second = wrap_up(tasks_client, WEEK)

    assert second.status_code == 200
    assert second.json() == first
    assert connection.execute(text("select count(*) from task_weeks")).scalar_one() == rows


def test_it_is_in_the_audit_log(tasks_client: TestClient, connection: Connection) -> None:
    tasks_client.get(f"/api/weeks/{NEXT_WEEK}")
    wrap_up(tasks_client, WEEK)

    actions = [
        row.action
        for row in connection.execute(text("select action from audit_log where action is not null"))
    ]
    assert "wrap up week" in actions


def test_mondays_close_after_a_wrap_up_finds_nothing_to_do(
    tasks_client: TestClient, connection: Connection, fixed_clock: FixedClock
) -> None:
    add_task(tasks_client, day="2026-11-22")
    tasks_client.get(f"/api/weeks/{NEXT_WEEK}")
    wrap_up(tasks_client, WEEK)
    before = connection.execute(text("select count(*) from audit_log")).scalar_one()

    fixed_clock.instant = MONDAY_MORNING
    assert tasks_client.get(f"/api/weeks/{NEXT_WEEK}").status_code == 200

    assert connection.execute(text("select count(*) from audit_log")).scalar_one() == before
