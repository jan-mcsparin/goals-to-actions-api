"""What goal reads count from tasks: this week's progress against a target, and a one-off
goal's steps."""

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.weeks import week_of
from tests.test_check_off import check_off, done_on
from tests.test_goals import ZONE, create_goal, lifting, no_sugar, today
from tests.test_milestones import page
from tests.test_tasks import add_task, one_off


@pytest.fixture
def tasks_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


def listed(client: TestClient, goal_id: str) -> Any:
    [goal] = [goal for goal in client.get("/api/goals").json()["goals"] if goal["id"] == goal_id]
    return goal


def week_goals(client: TestClient) -> Any:
    return client.get(f"/api/weeks/{week_of(today()).isoformat()}").json()["goals"]


def running() -> dict[str, Any]:
    return lifting(
        label="Run more",
        weeklyTarget={"kind": "amount", "sessions": 4, "amount": 25, "unit": "miles"},
    )


def test_count_progress_is_the_goals_tasks_done_this_week(tasks_client: TestClient) -> None:
    goal = create_goal(tasks_client, lifting())
    sessions = [add_task(tasks_client, goalId=goal["id"]) for _ in range(3)]
    add_task(tasks_client)  # not the goal's
    for session in sessions[:2]:
        check_off(tasks_client, session["id"])

    progress = {"done": 2, "of": 3}
    assert listed(tasks_client, goal["id"])["weekProgress"] == progress
    assert page(tasks_client, goal["id"])["weekProgress"] == progress
    assert week_goals(tasks_client) == [
        {
            "id": goal["id"],
            "label": "Be strong",
            "aspiration": None,
            "weeklyTarget": goal["weeklyTarget"],
            "progress": progress,
        }
    ]


def test_amount_progress_is_the_values_logged_this_week(tasks_client: TestClient) -> None:
    goal = create_goal(tasks_client, running())
    for miles in (5, 3.1):
        check_off(tasks_client, add_task(tasks_client, goalId=goal["id"])["id"], valueLogged=miles)
    check_off(tasks_client, add_task(tasks_client, goalId=goal["id"])["id"])  # nothing logged

    assert listed(tasks_client, goal["id"])["weekProgress"] == {"done": 8.1, "of": 25}


def test_a_task_counts_for_the_week_of_the_row_it_was_done_in(
    tasks_client: TestClient, connection: Connection
) -> None:
    goal = create_goal(tasks_client, lifting())
    this_week = add_task(tasks_client, goalId=goal["id"])
    the_sunday_before = (week_of(today()) - timedelta(days=1)).isoformat()
    check_off(tasks_client, this_week["id"], **done_on(the_sunday_before))
    last_week = add_task(tasks_client, goalId=goal["id"])
    connection.execute(
        text("update task_weeks set week = :week where task_id = :id"),
        {"week": week_of(today()) - timedelta(weeks=1), "id": last_week["id"]},
    )
    check_off(tasks_client, last_week["id"])

    assert listed(tasks_client, goal["id"])["weekProgress"] == {"done": 1, "of": 3}


def test_only_building_goals_with_a_target_this_week_have_progress(
    tasks_client: TestClient,
) -> None:
    paused = create_goal(tasks_client, lifting(label="Paused"))
    tasks_client.post(f"/api/goals/{paused['id']}/pause")
    quitting = create_goal(tasks_client, no_sugar())
    active = create_goal(tasks_client, lifting())

    assert listed(tasks_client, quitting["id"])["weekProgress"] is None
    assert listed(tasks_client, paused["id"])["weekProgress"] == {"done": 0, "of": 3}
    assert [goal["id"] for goal in week_goals(tasks_client)] == [active["id"]]


def test_a_one_off_goal_counts_its_steps_leaving_dropped_ones_out(
    tasks_client: TestClient, connection: Connection
) -> None:
    goal = one_off(tasks_client)
    steps = [add_task(tasks_client, title=f"Step {n}", goalId=goal["id"]) for n in range(1, 7)]
    # Each add is its own transaction in use; here they share one, and so one now().
    for n, step in enumerate(steps):
        connection.execute(
            text(
                "update tasks set created_at = created_at + :n * interval '1 second' where id = :id"
            ),
            {"n": n, "id": step["id"]},
        )
    for step in steps[:2]:
        check_off(tasks_client, step["id"])
    connection.execute(
        text("update tasks set state = 'dropped' where id = :id"), {"id": steps[5]["id"]}
    )

    goal_page = page(tasks_client, goal["id"])

    assert goal_page["progress"] == {"hit": 2, "of": 5}
    assert listed(tasks_client, goal["id"])["progress"] == {"hit": 2, "of": 5}
    assert [step["title"] for step in goal_page["steps"]] == [f"Step {n}" for n in range(1, 6)]
    assert [step["state"] for step in goal_page["steps"]] == ["done"] * 2 + ["open"] * 3
    assert goal_page["weekProgress"] is None


def test_a_reached_one_off_goal_counts_every_step(tasks_client: TestClient) -> None:
    goal = one_off(tasks_client)
    for n in range(3):
        add_task(tasks_client, title=f"Step {n}", goalId=goal["id"])
    tasks_client.post(f"/api/goals/{goal['id']}/mark-reached")

    assert page(tasks_client, goal["id"])["progress"] == {"hit": 3, "of": 3}


def test_other_goals_pages_list_no_steps(tasks_client: TestClient) -> None:
    goal = create_goal(tasks_client, lifting())
    add_task(tasks_client, goalId=goal["id"])

    assert page(tasks_client, goal["id"])["steps"] == []
