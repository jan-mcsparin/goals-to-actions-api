"""The queueable writes (ADR-010; shared decisions 13 to 15) when they arrive late: aimed at a
row that's gone, a task that's been set aside, or a week the task has left. Each answers 404
or 409, so the phone drops it, or lands as the person meant; never a 500. The test client
re-raises server errors, so a 500 fails here. And when two devices change one task, the last
write to arrive wins."""

from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from tests.conftest import FixedClock
from tests.test_check_off import done_on
from tests.test_goals import ZONE, create_goal, lifting, no_sugar, today
from tests.test_task_moves import this_week
from tests.test_tasks import add_task, open_next_week
from tests.test_wrap_up import NEXT_WEEK, SUNDAY_EVENING, WEEK

Send = Callable[[TestClient, str, str, str], Any]


@pytest.fixture
def tasks_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


def day() -> str:
    return today().isoformat()


def check_off(client: TestClient, task_id: str, week: str, other_id: str) -> Any:
    return client.post(f"/api/tasks/{task_id}/check-off", json=done_on(day()))


def uncheck(client: TestClient, task_id: str, week: str, other_id: str) -> Any:
    return client.post(f"/api/tasks/{task_id}/uncheck")


def place(client: TestClient, task_id: str, week: str, other_id: str) -> Any:
    return client.post(f"/api/tasks/{task_id}/place", json={"week": week, "day": day()})


def to_bank(client: TestClient, task_id: str, week: str, other_id: str) -> Any:
    return client.post(f"/api/tasks/{task_id}/bank", json={"week": week})


def swap_to_bank(client: TestClient, task_id: str, week: str, other_id: str) -> Any:
    """The task is the one going to the bank."""
    body = {"week": week, "bankTaskId": other_id, "day": day()}
    return client.post(f"/api/tasks/{task_id}/swap", json=body)


def swap_onto_day(client: TestClient, task_id: str, week: str, other_id: str) -> Any:
    """The task is the one being placed."""
    body = {"week": week, "bankTaskId": task_id, "day": day()}
    return client.post(f"/api/tasks/{other_id}/swap", json=body)


TASK_WRITES: dict[str, Send] = {
    "checkOffTask": check_off,
    "uncheckTask": uncheck,
    "placeTask": place,
    "moveTaskToBank": to_bank,
    "swapTasks to the bank": swap_to_bank,
    "swapTasks onto a day": swap_onto_day,
}
PLAN_EDITS = {
    name: send for name, send in TASK_WRITES.items() if name not in {"checkOffTask", "uncheckTask"}
}


def counterpart(client: TestClient, send: Send) -> str:
    """The other task in a swap: on today when the task is the one placed, else in the bank."""
    if send is swap_onto_day:
        return str(add_task(client, day=day())["id"])
    return str(add_task(client)["id"])


# A row that's gone


@pytest.mark.parametrize("name", TASK_WRITES)
def test_a_task_write_aimed_at_a_deleted_task_is_not_found(
    tasks_client: TestClient, name: str
) -> None:
    send = TASK_WRITES[name]
    task_id = add_task(tasks_client, day=day())["id"]
    other_id = counterpart(tasks_client, send)
    assert tasks_client.delete(f"/api/tasks/{task_id}").status_code == 204

    assert send(tasks_client, task_id, this_week().isoformat(), other_id).status_code == 404


def test_an_add_under_a_deleted_goal_is_not_found(tasks_client: TestClient) -> None:
    goal_id = create_goal(tasks_client, lifting())["id"]
    tasks_client.delete(f"/api/goals/{goal_id}")

    response = tasks_client.put(f"/api/tasks/{uuid4()}", json={"title": "Lift", "goalId": goal_id})

    assert response.status_code == 404


def test_an_add_resent_after_its_task_was_deleted_is_refused(tasks_client: TestClient) -> None:
    task_id = add_task(tasks_client)["id"]
    tasks_client.delete(f"/api/tasks/{task_id}")

    response = tasks_client.put(f"/api/tasks/{task_id}", json={"title": "Call the dentist"})

    assert response.status_code == 409


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("PUT", "quit-days/{day}", {"held": True}),
        ("POST", "quit-days/{day}/clear", None),
        ("PUT", "urges/{day}", {"level": "strong"}),
        ("POST", "urges/{day}/clear", None),
    ],
)
def test_a_quitting_write_aimed_at_a_deleted_goal_is_not_found(
    tasks_client: TestClient, method: str, path: str, body: dict[str, Any] | None
) -> None:
    goal_id = create_goal(tasks_client, no_sugar(startDate="2026-11-01"))["id"]
    tasks_client.delete(f"/api/goals/{goal_id}")

    url = f"/api/goals/{goal_id}/" + path.format(day=day())
    assert tasks_client.request(method, url, json=body).status_code == 404


# A task set aside


@pytest.mark.parametrize("name", PLAN_EDITS)
def test_a_plan_edit_aimed_at_a_set_aside_task_is_refused(
    tasks_client: TestClient, name: str
) -> None:
    send = PLAN_EDITS[name]
    goal_id = create_goal(tasks_client, lifting())["id"]
    task_id = add_task(tasks_client, day=day(), goalId=goal_id)["id"]
    other_id = counterpart(tasks_client, send)
    tasks_client.post(f"/api/goals/{goal_id}/pause")

    assert send(tasks_client, task_id, this_week().isoformat(), other_id).status_code == 409


def test_a_check_off_of_a_set_aside_task_still_lands(tasks_client: TestClient) -> None:
    # Done is done: a check-off queued before another device paused the goal still counts.
    goal_id = create_goal(tasks_client, lifting())["id"]
    task_id = add_task(tasks_client, day=day(), goalId=goal_id)["id"]
    tasks_client.post(f"/api/goals/{goal_id}/pause")

    response = tasks_client.post(f"/api/tasks/{task_id}/check-off", json=done_on(day()))

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "done"


# A week the task has left


@pytest.mark.parametrize("name", PLAN_EDITS)
def test_a_plan_edit_made_in_a_week_the_task_has_left_is_refused(
    tasks_client: TestClient, name: str
) -> None:
    send = PLAN_EDITS[name]
    # On tomorrow, so each edit would change something: one that changes nothing is a repeat.
    task_id = add_task(tasks_client, day=(today() + timedelta(days=1)).isoformat())["id"]
    other_id = counterpart(tasks_client, send)
    last_week = (this_week() - timedelta(weeks=1)).isoformat()

    assert send(tasks_client, task_id, last_week, other_id).status_code == 409


def test_a_check_off_in_a_week_not_yet_current_is_refused(
    tasks_client: TestClient, connection: Connection
) -> None:
    open_next_week(connection)
    next_monday = (this_week() + timedelta(weeks=1)).isoformat()
    task_id = add_task(tasks_client, dueDate=next_monday)["id"]

    response = tasks_client.post(f"/api/tasks/{task_id}/check-off", json=done_on(next_monday))

    assert response.status_code == 409


# A create aimed at a day no longer allowed


def test_an_add_onto_a_past_day_lands_in_the_current_weeks_bank(
    tasks_client: TestClient,
) -> None:
    yesterday = (today() - timedelta(days=1)).isoformat()

    task = add_task(tasks_client, day=yesterday)

    assert (task["week"], task["plannedDay"]) == (this_week().isoformat(), None)


def test_an_add_onto_today_after_a_wrap_up_lands_in_the_new_weeks_bank(
    tasks_client: TestClient, fixed_clock: FixedClock
) -> None:
    fixed_clock.instant = SUNDAY_EVENING
    tasks_client.get(f"/api/weeks/{NEXT_WEEK}")
    tasks_client.post(f"/api/weeks/{WEEK}/wrap-up")

    task = add_task(tasks_client, day="2026-11-22")

    assert (task["week"], task["plannedDay"]) == (NEXT_WEEK.isoformat(), None)


# Two devices


def test_the_last_edit_to_arrive_wins(tasks_client: TestClient) -> None:
    task_id = add_task(tasks_client)["id"]
    phone = {"title": "Call the dentist at 9", "dueDate": None, "timeOfDay": None}
    laptop = {"title": "Call the dentist on Friday", "dueDate": None, "timeOfDay": None}

    tasks_client.patch(f"/api/tasks/{task_id}", json=phone)
    tasks_client.patch(f"/api/tasks/{task_id}", json=laptop)

    week = tasks_client.get(f"/api/weeks/{this_week().isoformat()}").json()
    [shown] = [task for task in week["tasks"] if task["id"] == task_id]
    assert shown["title"] == "Call the dentist on Friday"
