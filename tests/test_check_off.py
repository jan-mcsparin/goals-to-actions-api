from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.weeks import week_of
from tests.test_aspirations import add_other_user, audit_rows
from tests.test_goals import ZONE, today
from tests.test_tasks import add_task, add_task_for, one_off, open_next_week, rows


@pytest.fixture
def tasks_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


def done_on(day: str, **more: Any) -> dict[str, Any]:
    return {"completedAt": f"{day}T07:30:00Z", "completedOn": day} | more


def check_off(client: TestClient, task_id: str, **body: Any) -> Any:
    response = client.post(
        f"/api/tasks/{task_id}/check-off", json=done_on(today().isoformat()) | body
    )
    assert response.status_code == 200, response.text
    return response.json()


def uncheck(client: TestClient, task_id: str) -> Any:
    response = client.post(f"/api/tasks/{task_id}/uncheck")
    assert response.status_code == 200, response.text
    return response.json()


def test_a_check_off_marks_the_task_and_its_row_done(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client, day=today().isoformat())

    done = check_off(tasks_client, task["id"], valueLogged=3.1)

    assert done == task | {
        "state": "done",
        "completedAt": f"{today().isoformat()}T07:30:00Z",
        "completedOn": today().isoformat(),
        "valueLogged": 3.1,
    }
    assert rows(connection, task["id"]) == [(week_of(today()), today(), True, "done")]
    assert [row.action for row in audit_rows(connection, task["id"])] == [
        "add task",
        "check off task",
    ]


def test_a_check_off_after_midnight_counts_for_the_day_the_phone_sent(
    tasks_client: TestClient,
) -> None:
    # 12:30 a.m. in Tokyo is still the day before in UTC.
    task = add_task(tasks_client)
    the_evening_before = (today() - timedelta(days=1)).isoformat()

    done = check_off(
        tasks_client,
        task["id"],
        completedAt=f"{the_evening_before}T15:30:00Z",
        completedOn=today().isoformat(),
    )

    assert done["completedOn"] == today().isoformat()


def test_a_bank_task_checked_off_stays_off_the_days(tasks_client: TestClient) -> None:
    task = add_task(tasks_client)

    assert check_off(tasks_client, task["id"])["plannedDay"] is None


def test_the_same_check_off_twice_changes_nothing_more(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client)
    first = check_off(tasks_client, task["id"])

    assert check_off(tasks_client, task["id"]) == first
    assert len(rows(connection, task["id"])) == 1


def test_a_waiting_step_checked_off_gets_a_done_row_on_that_day(
    tasks_client: TestClient, connection: Connection
) -> None:
    step = add_task(tasks_client, goalId=one_off(tasks_client)["id"])
    yesterday = today() - timedelta(days=1)

    done = check_off(tasks_client, step["id"], **done_on(yesterday.isoformat()))

    assert (done["week"], done["plannedDay"]) == (
        week_of(yesterday).isoformat(),
        yesterday.isoformat(),
    )
    assert rows(connection, step["id"]) == [(week_of(yesterday), yesterday, False, "done")]


def test_unchecking_a_waiting_step_leaves_it_on_the_day_it_was_done(
    tasks_client: TestClient, connection: Connection
) -> None:
    step = add_task(tasks_client, goalId=one_off(tasks_client)["id"])
    check_off(tasks_client, step["id"])

    unchecked = uncheck(tasks_client, step["id"])

    assert (unchecked["state"], unchecked["plannedDay"]) == ("open", today().isoformat())
    assert rows(connection, step["id"]) == [(week_of(today()), today(), False, None)]


def test_next_weeks_tasks_cannot_be_checked_off_yet(
    tasks_client: TestClient, connection: Connection
) -> None:
    open_next_week(connection)
    next_monday = week_of(today()) + timedelta(weeks=1)
    task = add_task(tasks_client, dueDate=next_monday.isoformat())

    response = tasks_client.post(
        f"/api/tasks/{task['id']}/check-off", json=done_on(today().isoformat())
    )

    assert response.status_code == 409


def test_a_dropped_task_cannot_be_checked_off(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client)
    connection.execute(
        text("update task_weeks set outcome = 'dropped' where task_id = :id"), {"id": task["id"]}
    )
    connection.execute(
        text("update tasks set state = 'dropped' where id = :id"), {"id": task["id"]}
    )

    response = tasks_client.post(
        f"/api/tasks/{task['id']}/check-off", json=done_on(today().isoformat())
    )

    assert response.status_code == 409


def test_another_users_task_is_not_found(tasks_client: TestClient, connection: Connection) -> None:
    theirs = add_task_for(connection, add_other_user(connection))

    assert (
        tasks_client.post(f"/api/tasks/{theirs}/check-off", json=done_on("2026-11-18")).status_code
        == 404
    )
    assert tasks_client.post(f"/api/tasks/{theirs}/uncheck").status_code == 404
    assert tasks_client.post(f"/api/tasks/{uuid4()}/uncheck").status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"completedOn": "2026-11-18"},
        {"completedAt": "2026-11-18T07:30:00", "completedOn": "2026-11-18"},
        done_on("2026-11-18", valueLogged=-1),
    ],
)
def test_a_check_off_needs_an_aware_moment_and_a_value_not_below_zero(
    tasks_client: TestClient, body: Any
) -> None:
    task = add_task(tasks_client)

    assert tasks_client.post(f"/api/tasks/{task['id']}/check-off", json=body).status_code == 422


# uncheckTask


def test_check_off_then_uncheck_leaves_the_task_as_it_was(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client, day=today().isoformat())
    check_off(tasks_client, task["id"], valueLogged=5)

    assert uncheck(tasks_client, task["id"]) == task
    assert rows(connection, task["id"]) == [(week_of(today()), today(), True, None)]


def test_the_same_uncheck_twice_changes_nothing_more(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client)
    check_off(tasks_client, task["id"])
    uncheck(tasks_client, task["id"])

    assert uncheck(tasks_client, task["id"]) == task
    assert [row.action for row in audit_rows(connection, task["id"])] == [
        "add task",
        "check off task",
        "uncheck task",
    ]
