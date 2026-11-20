"""Deleting a recurring item made by mistake (spec `delete`): its open tasks go with it, and
its other tasks stay as history with no item."""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from tests.conftest import FixedClock
from tests.test_aspirations import add_other_user, audit_rows
from tests.test_check_off import check_off, uncheck
from tests.test_goals import ZONE
from tests.test_item_tasks import NEXT_WEEK, SUNDAY_EVENING, WEDNESDAY, WEEK, item_tasks
from tests.test_recurring_items import add_item_for, create, item, listed
from tests.test_task_moves import drop

MONDAY_MORNING = datetime(2026, 11, 23, 16, 0, tzinfo=UTC)  # 9 a.m. in Denver


@pytest.fixture
def items_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


def stretch(client: TestClient) -> Any:
    return create(
        client,
        item(
            name="Stretch",
            schedule={"kind": "flexible", "times": 3, "period": "week"},
            startsOn=WEDNESDAY,
        ),
    )


def delete_item(client: TestClient, item_id: str) -> Any:
    return client.delete(f"/api/recurring-items/{item_id}")


def test_its_open_tasks_go_and_its_done_and_dropped_ones_stay_with_no_item(
    items_client: TestClient, connection: Connection
) -> None:
    created = stretch(items_client)
    done, dropped, _ = item_tasks(items_client, WEEK)
    check_off(items_client, done["id"])
    drop(items_client, dropped["id"])

    response = delete_item(items_client, created["id"])

    assert response.status_code == 204
    assert "content-type" not in response.headers
    left = item_tasks(items_client, WEEK)
    assert [task["id"] for task in left] == [done["id"]]
    assert left[0]["recurringItemId"] is None
    assert left[0]["origin"] == "recurringItem"
    assert listed(items_client) == []
    kept = connection.execute(
        text("select state, recurring_item_id from tasks where id = :id and deleted_at is null"),
        {"id": dropped["id"]},
    ).one()
    assert (kept.state, kept.recurring_item_id) == ("dropped", None)


def test_a_deleted_item_makes_no_tasks_when_next_week_opens(
    items_client: TestClient, fixed_clock: FixedClock
) -> None:
    created = stretch(items_client)
    delete_item(items_client, created["id"])

    fixed_clock.instant = SUNDAY_EVENING

    assert item_tasks(items_client, NEXT_WEEK) == []


def test_deleting_twice_changes_nothing_more(
    items_client: TestClient, connection: Connection
) -> None:
    created = stretch(items_client)
    delete_item(items_client, created["id"])

    assert delete_item(items_client, created["id"]).status_code == 204
    assert [row.action for row in audit_rows(connection, created["id"])] == [
        "create recurring item",
        "delete recurring item",
    ]


def test_another_users_item_or_an_unknown_id_is_not_found(
    items_client: TestClient, connection: Connection
) -> None:
    theirs = add_item_for(connection, add_other_user(connection))

    assert delete_item(items_client, str(theirs)).status_code == 404
    assert delete_item(items_client, str(uuid4())).status_code == 404


def test_a_done_task_it_left_can_be_unchecked_and_lapses_when_its_week_closes(
    items_client: TestClient, connection: Connection, fixed_clock: FixedClock
) -> None:
    created = stretch(items_client)
    done = item_tasks(items_client, WEEK)[0]
    check_off(items_client, done["id"])
    delete_item(items_client, created["id"])

    unchecked = uncheck(items_client, done["id"])

    assert (unchecked["state"], unchecked["recurringItemId"]) == ("open", None)
    assert done["id"] in [task["id"] for task in item_tasks(items_client, WEEK)]

    fixed_clock.instant = MONDAY_MORNING
    items_client.get(f"/api/weeks/{NEXT_WEEK}")

    state = connection.execute(
        text("select state from tasks where id = :id"), {"id": done["id"]}
    ).scalar_one()
    assert state == "lapsed"
    assert item_tasks(items_client, NEXT_WEEK) == []


def test_with_next_week_open_its_tasks_leave_both_weeks(
    items_client: TestClient, connection: Connection, fixed_clock: FixedClock
) -> None:
    created = stretch(items_client)
    fixed_clock.instant = SUNDAY_EVENING
    made = [task["id"] for week in (WEEK, NEXT_WEEK) for task in item_tasks(items_client, week)]
    assert item_tasks(items_client, NEXT_WEEK)  # next week is open and has its tasks

    delete_item(items_client, created["id"])

    assert item_tasks(items_client, WEEK) == []
    assert item_tasks(items_client, NEXT_WEEK) == []
    live = connection.execute(
        text(
            "select count(*) from task_weeks"
            " where task_id = any(cast(:ids as uuid[])) and deleted_at is null"
        ),
        {"ids": made},
    ).scalar_one()
    assert live == 0
