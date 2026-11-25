"""A fixed-day item's task stays on its day in the week it was due (API #47): moving it to the
bank, swapping it out or placing it on another day is refused. Once it has carried over it's
placed like any task."""

from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.weeks import week_of
from tests.test_check_off import check_off
from tests.test_goals import ZONE, today
from tests.test_recurring_items import create as create_item
from tests.test_recurring_items import item
from tests.test_task_moves import place, swap, to_bank
from tests.test_tasks import add_task

STAYS = "This one stays on its day."


@pytest.fixture
def tasks_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


def week_tasks(client: TestClient) -> list[Any]:
    response = client.get(f"/api/weeks/{week_of(today()).isoformat()}")
    assert response.status_code == 200, response.text
    tasks: list[Any] = response.json()["tasks"]
    return tasks


def todays_item(client: TestClient, kind: str = "weekly") -> Any:
    """A fixed-day item due today, and its task, on today."""
    schedule = (
        {"kind": "weekly", "weekday": today().strftime("%A").lower()}
        if kind == "weekly"
        else {"kind": "monthly", "dayOfMonth": today().day}
    )
    create_item(client, item(name="Water the plants", startsOn="2026-11-01", schedule=schedule))
    [task] = [task for task in week_tasks(client) if task["title"] == "Water the plants"]
    assert (task["plannedDay"], task["fixedDay"]) == (today().isoformat(), True)
    return task


def refused(response: Any) -> bool:
    return bool(response.status_code == 409 and response.json()["detail"] == STAYS)


def plants_day(client: TestClient) -> str | None:
    [task] = [task for task in week_tasks(client) if task["title"] == "Water the plants"]
    day: str | None = task["plannedDay"]
    return day


@pytest.mark.parametrize("kind", ["weekly", "monthly"])
def test_back_to_the_bank_is_refused(tasks_client: TestClient, kind: str) -> None:
    plants = todays_item(tasks_client, kind)

    assert refused(to_bank(tasks_client, plants["id"]))
    assert plants_day(tasks_client) == today().isoformat()


def test_swapping_it_out_is_refused_and_the_bank_task_stays_put(tasks_client: TestClient) -> None:
    plants = todays_item(tasks_client)
    in_bank = add_task(tasks_client, title="In the bank")

    assert refused(swap(tasks_client, plants["id"], in_bank["id"], today()))
    assert plants_day(tasks_client) == today().isoformat()
    [bank] = [task for task in week_tasks(tasks_client) if task["id"] == in_bank["id"]]
    assert bank["plannedDay"] is None


def test_placing_it_on_another_day_is_refused(tasks_client: TestClient) -> None:
    plants = todays_item(tasks_client)

    assert refused(place(tasks_client, plants["id"], today() + timedelta(days=1)))
    assert plants_day(tasks_client) == today().isoformat()


def test_placing_it_in_a_later_week_is_refused(tasks_client: TestClient) -> None:
    plants = todays_item(tasks_client)

    response = place(tasks_client, plants["id"], today() + timedelta(weeks=3), week_of(today()))

    assert response.status_code == 409
    assert plants_day(tasks_client) == today().isoformat()


def test_placing_it_on_its_own_day_and_checking_it_off_still_work(
    tasks_client: TestClient,
) -> None:
    plants = todays_item(tasks_client)

    assert place(tasks_client, plants["id"], today()).status_code == 200
    check_off(tasks_client, plants["id"])
    assert tasks_client.post(f"/api/tasks/{plants['id']}/uncheck").status_code == 200


def test_a_flexible_items_task_can_still_move(tasks_client: TestClient) -> None:
    create_item(
        tasks_client,
        item(name="Laundry", schedule={"kind": "flexible", "times": 1, "period": "week"}),
    )
    [laundry] = [task for task in week_tasks(tasks_client) if task["title"] == "Laundry"]

    assert to_bank(tasks_client, laundry["id"]).status_code == 200


def test_one_that_carried_over_moves_like_any_task(
    tasks_client: TestClient, connection: Connection
) -> None:
    plants = todays_item(tasks_client)
    connection.execute(
        text(
            "insert into task_weeks (id, user_id, task_id, week, outcome)"
            " select :id, user_id, id, :week, 'rolled_over' from tasks where id = :task"
        ),
        {"id": uuid4(), "week": week_of(today()) - timedelta(weeks=1), "task": plants["id"]},
    )

    assert to_bank(tasks_client, plants["id"]).status_code == 200
    assert plants_day(tasks_client) is None


def test_a_queued_move_sent_again_is_still_refused(tasks_client: TestClient) -> None:
    """The phone drops a write on 409; one resent anyway changes nothing."""
    plants = todays_item(tasks_client)

    assert refused(to_bank(tasks_client, plants["id"]))
    assert refused(to_bank(tasks_client, plants["id"]))
    assert plants_day(tasks_client) == today().isoformat()
