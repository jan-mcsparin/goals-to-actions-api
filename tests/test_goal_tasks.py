"""Pausing, ending or reaching a goal sets its unfinished tasks aside; resume, reopen and go
again bring them back."""

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.weeks import week_of
from tests.test_aspirations import create as create_aspiration
from tests.test_check_off import check_off
from tests.test_goals import ZONE, create_goal, lifting, today
from tests.test_tasks import add_task, open_next_week, rows

# The change that leaves active, and the one that comes back from it.
AWAY_AND_BACK = [("pause", "resume"), ("end", "go-again"), ("mark-reached", "reopen")]


@pytest.fixture
def tasks_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


def change(client: TestClient, goal_id: str, route: str) -> None:
    response = client.post(f"/api/goals/{goal_id}/{route}")
    assert response.status_code == 200, response.text


def week_titles(client: TestClient, week: Any) -> list[str]:
    """The titles of the week's tasks, leaving out the goals' own sessions."""
    tasks = client.get(f"/api/weeks/{week.isoformat()}").json()["tasks"]
    return [task["title"] for task in tasks if task["origin"] != "weeklyTarget"]


def goal_with_tasks(client: TestClient) -> tuple[str, dict[str, Any]]:
    goal_id = create_goal(client, lifting())["id"]
    tasks = {
        "bank": add_task(client, title="Bank", goalId=goal_id),
        "day": add_task(client, title="Day", goalId=goal_id, day=today().isoformat()),
        "done": add_task(client, title="Done", goalId=goal_id),
        "waiting": add_task(
            client,
            title="Waiting",
            goalId=goal_id,
            dueDate=(today() + timedelta(days=9)).isoformat(),
        ),
    }
    check_off(client, tasks["done"]["id"])
    return goal_id, tasks


@pytest.mark.parametrize(("away", "back"), AWAY_AND_BACK)
def test_leaving_active_sets_unfinished_tasks_aside_keeping_their_day(
    tasks_client: TestClient, connection: Connection, away: str, back: str
) -> None:
    goal_id, tasks = goal_with_tasks(tasks_client)
    this_week = week_of(today())

    change(tasks_client, goal_id, away)

    assert week_titles(tasks_client, this_week) == ["Done"]
    assert rows(connection, tasks["day"]["id"]) == [(this_week, today(), True, "set_aside")]
    assert rows(connection, tasks["bank"]["id"]) == [(this_week, None, False, "set_aside")]
    assert rows(connection, tasks["waiting"]["id"]) == []


@pytest.mark.parametrize(("away", "back"), AWAY_AND_BACK)
def test_coming_back_returns_set_aside_tasks_to_their_weeks_bank(
    tasks_client: TestClient, connection: Connection, away: str, back: str
) -> None:
    goal_id, tasks = goal_with_tasks(tasks_client)
    this_week = week_of(today())
    change(tasks_client, goal_id, away)

    change(tasks_client, goal_id, back)

    assert sorted(week_titles(tasks_client, this_week)) == ["Bank", "Day", "Done"]
    assert rows(connection, tasks["day"]["id"]) == [(this_week, None, False, None)]
    assert rows(connection, tasks["waiting"]["id"]) == []


def test_next_weeks_tasks_are_set_aside_too(
    tasks_client: TestClient, connection: Connection
) -> None:
    open_next_week(connection)
    next_week = week_of(today()) + timedelta(weeks=1)
    goal_id = create_goal(tasks_client, lifting())["id"]
    task = add_task(tasks_client, goalId=goal_id, dueDate=next_week.isoformat())

    change(tasks_client, goal_id, "pause")

    assert rows(connection, task["id"]) == [(next_week, None, False, "set_aside")]
    change(tasks_client, goal_id, "resume")
    assert rows(connection, task["id"]) == [(next_week, None, False, None)]


def test_a_task_added_by_hand_whose_week_closed_comes_back_in_this_weeks_bank(
    tasks_client: TestClient, connection: Connection
) -> None:
    goal_id = create_goal(tasks_client, lifting())["id"]
    task = add_task(tasks_client, goalId=goal_id)
    session = add_task(tasks_client, goalId=goal_id)
    change(tasks_client, goal_id, "pause")
    last_week = week_of(today()) - timedelta(weeks=1)
    connection.execute(
        text("update task_weeks set week = :week where task_id in (:task, :session)"),
        {"week": last_week, "task": task["id"], "session": session["id"]},
    )
    connection.execute(
        text(
            "update tasks set origin = 'weekly_target', period_start = :week, number = 1"
            " where id = :id"
        ),
        {"week": last_week, "id": session["id"]},
    )

    change(tasks_client, goal_id, "resume")

    this_week = week_of(today())
    assert rows(connection, task["id"]) == [
        (last_week, None, False, "set_aside"),
        (this_week, None, False, None),
    ]
    assert rows(connection, session["id"]) == [(last_week, None, False, "set_aside")]


def test_a_status_change_sent_twice_moves_no_task_twice(
    tasks_client: TestClient, connection: Connection
) -> None:
    goal_id, tasks = goal_with_tasks(tasks_client)
    change(tasks_client, goal_id, "pause")
    change(tasks_client, goal_id, "end")  # from paused: nothing more to set aside
    change(tasks_client, goal_id, "go-again")
    change(tasks_client, goal_id, "go-again")

    assert rows(connection, tasks["bank"]["id"]) == [(week_of(today()), None, False, None)]


def test_retiring_an_aspiration_with_its_work_paused_sets_its_goals_tasks_aside(
    tasks_client: TestClient, connection: Connection
) -> None:
    open_next_week(connection)
    aspiration = create_aspiration(tasks_client, "Be fit")
    goal_id = create_goal(tasks_client, lifting(aspirationId=aspiration["id"]))["id"]
    this_week = week_of(today())
    next_week = this_week + timedelta(weeks=1)
    placed = add_task(tasks_client, title="Day", goalId=goal_id, day=today().isoformat())
    later = add_task(tasks_client, title="Later", goalId=goal_id, dueDate=next_week.isoformat())
    done = add_task(tasks_client, title="Done", goalId=goal_id)
    check_off(tasks_client, done["id"])

    response = tasks_client.post(
        f"/api/aspirations/{aspiration['id']}/retire", json={"itsWork": "pause"}
    )

    assert response.status_code == 200, response.text
    assert rows(connection, placed["id"]) == [(this_week, today(), True, "set_aside")]
    assert rows(connection, later["id"]) == [(next_week, None, False, "set_aside")]
    assert week_titles(tasks_client, this_week) == ["Done"]


def test_retiring_an_aspiration_keeping_its_work_leaves_its_goals_tasks(
    tasks_client: TestClient, connection: Connection
) -> None:
    aspiration = create_aspiration(tasks_client, "Be fit")
    goal_id = create_goal(tasks_client, lifting(aspirationId=aspiration["id"]))["id"]
    placed = add_task(tasks_client, title="Day", goalId=goal_id, day=today().isoformat())

    tasks_client.post(f"/api/aspirations/{aspiration['id']}/retire", json={"itsWork": "keep"})

    assert rows(connection, placed["id"]) == [(week_of(today()), today(), True, None)]
