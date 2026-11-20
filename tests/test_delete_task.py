"""Deleting a task made by mistake (spec `delete`): it and its week records are hidden
everywhere, and a deleted session isn't made again."""

from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.config import FIXED_USER_ID
from tests.conftest import FixedClock
from tests.test_aspirations import add_other_user, audit_rows
from tests.test_check_off import check_off
from tests.test_goal_sessions import NEXT_WEEK, SUNDAY_EVENING, WEEK, sessions
from tests.test_goals import ZONE, create_goal, lifting, today
from tests.test_tasks import add_task, add_task_for


@pytest.fixture
def tasks_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


def delete_task(client: TestClient, task_id: str) -> Any:
    return client.delete(f"/api/tasks/{task_id}")


def week_ids(client: TestClient, week: date = WEEK) -> list[str]:
    return [task["id"] for task in client.get(f"/api/weeks/{week}").json()["tasks"]]


def live_rows(connection: Connection, task_id: str) -> int:
    found = connection.execute(
        text("select count(*) from task_weeks where task_id = :id and deleted_at is null"),
        {"id": task_id},
    ).scalar_one()
    return int(found)


def test_a_deleted_task_leaves_the_week_with_its_rows(
    tasks_client: TestClient, connection: Connection
) -> None:
    on_today = add_task(tasks_client, plannedDay=today().isoformat())
    kept = add_task(tasks_client)

    response = delete_task(tasks_client, on_today["id"])

    assert response.status_code == 204
    assert "content-type" not in response.headers
    assert response.content == b""
    assert week_ids(tasks_client) == [kept["id"]]
    assert live_rows(connection, on_today["id"]) == 0


def test_a_deleted_waiting_task_leaves_the_upcoming_list(tasks_client: TestClient) -> None:
    waiting = add_task(tasks_client, dueDate=(today() + timedelta(weeks=3)).isoformat())

    delete_task(tasks_client, waiting["id"])

    assert tasks_client.get("/api/tasks/upcoming").json()["tasks"] == []


def test_a_deleted_done_session_no_longer_counts(tasks_client: TestClient) -> None:
    goal = create_goal(tasks_client, lifting())
    session = sessions(tasks_client, WEEK)[0]
    check_off(tasks_client, session["id"])

    delete_task(tasks_client, session["id"])

    listed = tasks_client.get("/api/goals").json()["goals"]
    assert [found["weekProgress"]["done"] for found in listed if found["id"] == goal["id"]] == [0]


def test_a_deleted_session_is_not_made_again_when_its_week_opens_again(
    tasks_client: TestClient, connection: Connection, fixed_clock: FixedClock
) -> None:
    create_goal(tasks_client, lifting())
    fixed_clock.instant = SUNDAY_EVENING
    first, *others = sessions(tasks_client, NEXT_WEEK)
    delete_task(tasks_client, first["id"])

    connection.execute(
        text("update users set planned_through_week = :week where id = :id"),
        {"week": WEEK, "id": FIXED_USER_ID},
    )

    assert [task["id"] for task in sessions(tasks_client, NEXT_WEEK)] == [
        task["id"] for task in others
    ]


def test_deleting_twice_changes_nothing_more(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client)
    delete_task(tasks_client, task["id"])

    assert delete_task(tasks_client, task["id"]).status_code == 204
    assert [row.action for row in audit_rows(connection, task["id"])] == [
        "add task",
        "delete task",
    ]


def test_another_users_task_or_an_unknown_id_is_not_found(
    tasks_client: TestClient, connection: Connection
) -> None:
    theirs = add_task_for(connection, add_other_user(connection))

    assert delete_task(tasks_client, str(theirs)).status_code == 404
    assert delete_task(tasks_client, str(uuid4())).status_code == 404
