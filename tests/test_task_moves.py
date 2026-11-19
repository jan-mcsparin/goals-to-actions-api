"""The plan edits: place on a day, back to the bank, swap and drop. Each names the week it
was made in, and is refused once the task has left it."""

from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.weeks import week_of
from tests.test_aspirations import add_other_user
from tests.test_check_off import check_off
from tests.test_goals import ZONE, today
from tests.test_tasks import add_task, add_task_for, open_next_week, row_actions, rows


@pytest.fixture
def tasks_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


def this_week() -> date:
    return week_of(today())


def next_week() -> date:
    return this_week() + timedelta(weeks=1)


def last_day_this_week() -> date:
    return this_week() + timedelta(days=6)


def place(client: TestClient, task_id: str, day: date, week: date | None = None) -> Any:
    week = week or week_of(day)
    return client.post(
        f"/api/tasks/{task_id}/place", json={"week": week.isoformat(), "day": day.isoformat()}
    )


def to_bank(client: TestClient, task_id: str, week: date | None = None) -> Any:
    return client.post(
        f"/api/tasks/{task_id}/bank", json={"week": (week or this_week()).isoformat()}
    )


def move_to_last_week(connection: Connection, task_id: str) -> None:
    connection.execute(
        text("update task_weeks set week = :week, planned_day = null where task_id = :id"),
        {"week": this_week() - timedelta(weeks=1), "id": task_id},
    )


# placeTask


def test_placing_puts_a_bank_task_on_a_day_placed_by_hand(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client)

    response = place(tasks_client, task["id"], today())

    assert response.status_code == 200, response.text
    assert response.json() == task | {"plannedDay": today().isoformat(), "placedByHand": True}
    assert row_actions(connection, task["id"]) == ["add task", "place task"]


def test_placing_moves_a_task_to_another_day(tasks_client: TestClient) -> None:
    task = add_task(tasks_client, day=today().isoformat())

    moved = place(tasks_client, task["id"], last_day_this_week()).json()

    assert moved["plannedDay"] == last_day_this_week().isoformat()


def test_the_same_placing_twice_changes_nothing_more(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client)
    first = place(tasks_client, task["id"], today()).json()

    assert place(tasks_client, task["id"], today()).json() == first
    assert rows(connection, task["id"]) == [(this_week(), today(), True, None)]


def test_next_weeks_tasks_can_be_placed_on_its_days(
    tasks_client: TestClient, connection: Connection
) -> None:
    open_next_week(connection)
    task = add_task(tasks_client, dueDate=next_week().isoformat())

    response = place(tasks_client, task["id"], next_week() + timedelta(days=2))

    assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    "day",
    [
        lambda: today() - timedelta(days=1),
        lambda: this_week() + timedelta(weeks=1),
    ],
    ids=["a past day", "a day in another week"],
)
def test_placing_on_a_day_not_allowed_is_refused(tasks_client: TestClient, day: Any) -> None:
    task = add_task(tasks_client)

    assert place(tasks_client, task["id"], day(), week=this_week()).status_code == 409


def test_a_placing_made_in_a_week_the_task_has_left_is_refused(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client)
    move_to_last_week(connection, task["id"])

    assert place(tasks_client, task["id"], today(), week=this_week()).status_code == 409
    assert to_bank(tasks_client, task["id"]).status_code == 409


def test_a_task_not_in_play_cannot_be_placed(tasks_client: TestClient) -> None:
    waiting = add_task(tasks_client, dueDate=(today() + timedelta(days=8)).isoformat())
    done = add_task(tasks_client)
    check_off(tasks_client, done["id"])

    assert place(tasks_client, waiting["id"], today()).status_code == 409
    assert place(tasks_client, done["id"], today()).status_code == 409


def test_another_users_task_is_not_found(tasks_client: TestClient, connection: Connection) -> None:
    theirs = str(add_task_for(connection, add_other_user(connection)))

    assert place(tasks_client, theirs, today()).status_code == 404
    assert to_bank(tasks_client, theirs).status_code == 404
    assert to_bank(tasks_client, str(uuid4())).status_code == 404


# moveTaskToBank


def test_back_to_the_bank_clears_the_day_and_the_mark(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client, day=today().isoformat())

    response = to_bank(tasks_client, task["id"])

    assert response.status_code == 200, response.text
    assert response.json() == task | {"plannedDay": None, "placedByHand": False}
    assert to_bank(tasks_client, task["id"]).json() == response.json()
    assert rows(connection, task["id"]) == [(this_week(), None, False, None)]
    assert row_actions(connection, task["id"])[-1] == "move task to bank"
