"""A recurring item's tasks in the open weeks: made when it's created or turned on, left alone
by an edit (spec `week-turnover`)."""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from tests.conftest import FixedClock
from tests.test_goals import ZONE
from tests.test_recurring_items import create, item, turn

WEEK = date(2026, 11, 16)
NEXT_WEEK = date(2026, 11, 23)
WEDNESDAY = "2026-11-18"
SATURDAY = datetime(2026, 11, 21, 17, 0, tzinfo=UTC)
SUNDAY_EVENING = datetime(2026, 11, 23, 2, 0, tzinfo=UTC)


@pytest.fixture
def items_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


def weekly(name: str, weekday: str) -> dict[str, Any]:
    return item(name=name, schedule={"kind": "weekly", "weekday": weekday}, startsOn=WEDNESDAY)


def item_tasks(client: TestClient, week: date) -> list[Any]:
    tasks = client.get(f"/api/weeks/{week}").json()["tasks"]
    return [task for task in tasks if task["origin"] == "recurringItem"]


def test_a_weekly_item_for_thursday_created_on_wednesday_has_this_weeks_task(
    items_client: TestClient,
) -> None:
    create(items_client, weekly("Water the plants", "thursday"))

    assert [task["title"] for task in item_tasks(items_client, WEEK)] == ["Water the plants"]


def test_a_weekly_item_for_tuesday_created_on_wednesday_waits_for_next_week(
    items_client: TestClient,
) -> None:
    create(items_client, weekly("Take out the trash", "tuesday"))

    assert item_tasks(items_client, WEEK) == []


def test_a_flexible_item_created_on_saturday_has_two_of_its_three(
    items_client: TestClient, fixed_clock: FixedClock
) -> None:
    fixed_clock.instant = SATURDAY

    create(
        items_client,
        item(
            name="Stretch",
            schedule={"kind": "flexible", "times": 3, "period": "week"},
            startsOn="2026-11-21",
        ),
    )

    assert len(item_tasks(items_client, WEEK)) == 2


def test_turned_off_and_on_in_the_same_week_it_gets_its_old_tasks_back(
    items_client: TestClient,
) -> None:
    created = create(items_client, weekly("Water the plants", "thursday"))
    before = [task["id"] for task in item_tasks(items_client, WEEK)]

    turn(items_client, created["id"], "off")
    assert item_tasks(items_client, WEEK) == []
    turn(items_client, created["id"], "on")

    assert [task["id"] for task in item_tasks(items_client, WEEK)] == before


def test_turned_on_in_a_later_week_it_gets_that_weeks_tasks(
    items_client: TestClient, fixed_clock: FixedClock
) -> None:
    created = create(items_client, weekly("Water the plants", "thursday"))
    turn(items_client, created["id"], "off")

    fixed_clock.instant = datetime(2026, 11, 25, 19, 0, tzinfo=UTC)
    turn(items_client, created["id"], "on")

    assert [task["title"] for task in item_tasks(items_client, NEXT_WEEK)] == ["Water the plants"]


def test_an_edit_leaves_this_weeks_task_and_takes_effect_next_period(
    items_client: TestClient, fixed_clock: FixedClock, connection: Connection
) -> None:
    created = create(items_client, weekly("Water the plants", "tuesday"))
    created_edit = items_client.patch(
        f"/api/recurring-items/{created['id']}",
        json={
            "name": "Water the plants",
            "schedule": {"kind": "weekly", "weekday": "thursday"},
            "startsOn": WEDNESDAY,
        },
    )
    assert created_edit.status_code == 200, created_edit.text
    assert item_tasks(items_client, WEEK) == []  # Tuesday had passed; the edit moves nothing

    fixed_clock.instant = SUNDAY_EVENING
    items_client.get(f"/api/weeks/{NEXT_WEEK}")  # opens next week, on Thursday's schedule

    assert len(item_tasks(items_client, NEXT_WEEK)) == 1
    count = connection.execute(
        text("select count(*) from tasks where recurring_item_id = :id"), {"id": created["id"]}
    ).scalar_one()
    assert count == 1


def days_of(client: TestClient, week: date) -> list[Any]:
    return [task["plannedDay"] for task in item_tasks(client, week)]


def test_a_weekly_item_for_today_goes_on_today(items_client: TestClient) -> None:
    create(items_client, weekly("Water the plants", "wednesday"))

    assert days_of(items_client, WEEK) == [WEDNESDAY]


def test_a_weekly_item_for_a_later_day_goes_on_its_day(items_client: TestClient) -> None:
    create(items_client, weekly("Water the plants", "friday"))

    assert days_of(items_client, WEEK) == ["2026-11-20"]


def test_a_monthly_item_for_today_goes_on_today(items_client: TestClient) -> None:
    create(
        items_client,
        item(
            name="Check the smoke alarm",
            schedule={"kind": "monthly", "dayOfMonth": 18},
            startsOn=WEDNESDAY,
        ),
    )

    assert days_of(items_client, WEEK) == [WEDNESDAY]


def test_an_item_for_today_sent_twice_changes_nothing_more(items_client: TestClient) -> None:
    body = weekly("Water the plants", "wednesday")
    item_id = create(items_client, body)["id"]
    before = item_tasks(items_client, WEEK)

    create(items_client, body, item_id)

    assert item_tasks(items_client, WEEK) == before


def test_an_item_for_today_turned_on_in_a_later_week_goes_on_today(
    items_client: TestClient, fixed_clock: FixedClock
) -> None:
    created = create(items_client, weekly("Water the plants", "wednesday"))
    turn(items_client, created["id"], "off")
    fixed_clock.instant = datetime(2026, 11, 25, 19, 0, tzinfo=UTC)

    turn(items_client, created["id"], "on")

    assert days_of(items_client, NEXT_WEEK) == ["2026-11-25"]
