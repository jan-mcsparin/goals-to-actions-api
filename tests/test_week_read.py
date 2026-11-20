from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.weeks import week_of
from tests.test_aspirations import add_other_user
from tests.test_check_off import check_off
from tests.test_goals import ZONE, create_goal, lifting, today
from tests.test_tasks import add_task, open_next_week


@pytest.fixture
def tasks_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


def this_week() -> str:
    return week_of(today()).isoformat()


def get_week(client: TestClient, week: str) -> Any:
    response = client.get(f"/api/weeks/{week}")
    assert response.status_code == 200, response.text
    return response.json()


def titles(week: Any) -> list[str]:
    """Titles of the tasks added by hand; a goal's own sessions are left out."""
    return [task["title"] for task in week["tasks"] if task["origin"] == "byHand"]


def test_the_week_lists_its_days_then_its_bank(tasks_client: TestClient) -> None:
    goal = create_goal(tasks_client, lifting())
    add_task(tasks_client, title="In the bank", goalId=goal["id"])
    add_task(
        tasks_client,
        title="At six",
        day=today().isoformat(),
        timeOfDay={"kind": "at", "time": "18:00"},
    )
    add_task(tasks_client, title="Today", day=today().isoformat())
    add_task(tasks_client, title="Waiting", dueDate=(today() + timedelta(days=8)).isoformat())

    week = get_week(tasks_client, this_week())

    assert (week["week"], week["isCurrent"], week["nextWeekOpen"]) == (this_week(), True, False)
    assert titles(week) == ["At six", "Today", "In the bank"]
    assert week["tasks"][2]["goalLabel"] == "Be strong"


def test_next_week_reads_as_open_once_it_is(
    tasks_client: TestClient, connection: Connection
) -> None:
    open_next_week(connection)
    next_week = (week_of(today()) + timedelta(weeks=1)).isoformat()

    week = get_week(tasks_client, next_week)

    assert (week["isCurrent"], week["nextWeekOpen"]) == (False, True)
    assert get_week(tasks_client, this_week())["nextWeekOpen"] is True


def test_the_week_shows_how_often_a_task_carried_over(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client)
    for weeks_ago in (2, 1):
        connection.execute(
            text(
                "insert into task_weeks (id, user_id, task_id, week, outcome)"
                " select :id, user_id, id, :week, 'rolled_over' from tasks where id = :task"
            ),
            {
                "id": uuid4(),
                "task": task["id"],
                "week": week_of(today()) - timedelta(weeks=weeks_ago),
            },
        )

    [shown] = get_week(tasks_client, this_week())["tasks"]

    assert shown["carriedOver"] == 2
    edited = tasks_client.patch(f"/api/tasks/{task['id']}", json={"title": task["title"]})
    assert edited.json()["carriedOver"] == 2  # a write's task counts as the week read does
    last_week = (week_of(today()) - timedelta(weeks=1)).isoformat()
    assert get_week(tasks_client, last_week)["tasks"] == []


def test_set_aside_rows_and_other_users_tasks_are_not_shown(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client)
    connection.execute(
        text("update task_weeks set outcome = 'set_aside' where task_id = :id"), {"id": task["id"]}
    )
    other = add_other_user(connection)
    theirs = uuid4()
    values = {"id": theirs, "row": uuid4(), "user": other, "week": week_of(today())}
    connection.execute(
        text(
            "insert into tasks (id, user_id, title, origin)"
            " values (:id, :user, 'Theirs', 'by_hand')"
        ),
        values,
    )
    connection.execute(
        text(
            "insert into task_weeks (id, user_id, task_id, week) values (:row, :user, :id, :week)"
        ),
        values,
    )

    assert get_week(tasks_client, this_week())["tasks"] == []


def test_a_week_is_named_by_its_monday(tasks_client: TestClient) -> None:
    tuesday = (week_of(today()) + timedelta(days=1)).isoformat()

    response = tasks_client.get(f"/api/weeks/{tuesday}")

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["path", "week"]


def day_marks(client: TestClient) -> dict[str, Any]:
    return {mark["day"]: mark for mark in get_week(client, this_week())["days"]}


def test_the_week_has_seven_days_with_the_normal_cap(tasks_client: TestClient) -> None:
    marks = get_week(tasks_client, this_week())["days"]

    first = week_of(today())
    assert [mark["day"] for mark in marks] == [
        (first + timedelta(days=n)).isoformat() for n in range(7)
    ]
    assert all(mark["cap"] == 4 and not mark["full"] for mark in marks)


def test_a_day_is_full_at_the_cap(tasks_client: TestClient) -> None:
    day = today().isoformat()
    for n in range(3):
        add_task(tasks_client, title=f"Task {n}", day=day)
    assert not day_marks(tasks_client)[day]["full"]

    add_task(tasks_client, title="Fourth", day=day)

    assert day_marks(tasks_client)[day]["full"]


def test_a_done_task_counts_and_a_dropped_one_does_not(tasks_client: TestClient) -> None:
    day = today().isoformat()
    tasks = [add_task(tasks_client, title=f"Task {n}", day=day) for n in range(4)]
    check_off(tasks_client, tasks[0]["id"])
    assert day_marks(tasks_client)[day]["full"]

    response = tasks_client.post(f"/api/tasks/{tasks[1]['id']}/drop")
    assert response.status_code == 200, response.text

    assert not day_marks(tasks_client)[day]["full"]


def test_changing_intensity_changes_only_the_mark(
    tasks_client: TestClient, connection: Connection
) -> None:
    day = today().isoformat()
    for n in range(3):
        add_task(tasks_client, title=f"Task {n}", day=day)
    before = get_week(tasks_client, this_week())

    connection.execute(text("update users set intensity = 'easing_off'"))
    after = get_week(tasks_client, this_week())

    assert after["tasks"] == before["tasks"]
    assert {mark["cap"] for mark in after["days"]} == {3}
    assert [mark["day"] for mark in after["days"] if mark["full"]] == [day]

    connection.execute(text("update users set intensity = 'going_hard'"))
    assert {mark["cap"] for mark in get_week(tasks_client, this_week())["days"]} == {6}
