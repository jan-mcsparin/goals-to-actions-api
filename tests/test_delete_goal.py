"""Deleting a goal made by mistake (spec `delete`): it goes with everything it had, and an
item continued from it stays."""

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from tests.test_aspirations import add_other_user, audit_rows
from tests.test_check_ins import check_in
from tests.test_check_off import check_off
from tests.test_goal_sessions import WEEK, sessions
from tests.test_goals import ZONE, add_goal_for, create_goal, lifting, no_sugar, today
from tests.test_milestones import add_milestone, page
from tests.test_quit_days import answer
from tests.test_recurring_items import create, item, listed
from tests.test_tasks import add_task
from tests.test_urges import rate

TABLES_WITH_A_GOAL = (
    "tasks",
    "milestones",
    "check_ins",
    "weekly_targets",
    "quit_days",
    "urge_ratings",
)


@pytest.fixture
def goals_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


def delete_goal(client: TestClient, goal_id: str) -> Any:
    return client.delete(f"/api/goals/{goal_id}")


def live_rows(connection: Connection, goal_id: str) -> dict[str, int]:
    """What the goal still has that isn't deleted, by table."""
    counts = {
        table: connection.execute(
            text(f"select count(*) from {table} where goal_id = :id and deleted_at is null"),
            {"id": goal_id},
        ).scalar_one()
        for table in TABLES_WITH_A_GOAL
    }
    counts["task_weeks"] = connection.execute(
        text(
            "select count(*) from task_weeks join tasks on tasks.id = task_weeks.task_id"
            " where tasks.goal_id = :id and task_weeks.deleted_at is null"
        ),
        {"id": goal_id},
    ).scalar_one()
    return {table: count for table, count in counts.items() if count}


def is_gone(client: TestClient, goal_id: str) -> bool:
    listed_ids = [goal["id"] for goal in client.get("/api/goals").json()["goals"]]
    return client.get(f"/api/goals/{goal_id}").status_code == 404 and goal_id not in listed_ids


def test_a_building_goal_goes_with_its_sessions_milestones_and_check_ins(
    goals_client: TestClient, connection: Connection
) -> None:
    goal = create_goal(goals_client, lifting())
    check_off(goals_client, sessions(goals_client, WEEK)[0]["id"])
    add_milestone(goals_client, goal["id"], "Bench 135")
    first = page(goals_client, goal["id"])["milestones"][0]["id"]
    assert check_in(goals_client, goal["id"], first, result="Bench 137").status_code == 200
    assert live_rows(connection, goal["id"])  # it has something to lose

    response = delete_goal(goals_client, goal["id"])

    assert response.status_code == 204
    assert "content-type" not in response.headers
    assert is_gone(goals_client, goal["id"])
    assert sessions(goals_client, WEEK) == []
    assert live_rows(connection, goal["id"]) == {}


def test_a_quitting_goal_goes_with_its_days_and_urges(
    goals_client: TestClient, connection: Connection
) -> None:
    goal = create_goal(goals_client, no_sugar())
    assert answer(goals_client, goal["id"], today().isoformat(), True).status_code == 200
    assert rate(goals_client, goal["id"], today().isoformat(), "low").status_code == 200

    delete_goal(goals_client, goal["id"])

    assert is_gone(goals_client, goal["id"])
    assert goals_client.get(f"/api/weeks/{WEEK}").json()["quittingGoals"] == []
    assert live_rows(connection, goal["id"]) == {}


def test_a_one_off_goal_goes_with_its_steps(
    goals_client: TestClient, connection: Connection
) -> None:
    goal = create_goal(
        goals_client, {"type": "oneOff", "label": "Move house", "measurableLine": "Keys handed in"}
    )
    add_task(goals_client, title="Pack", goalId=goal["id"], plannedDay=today().isoformat())
    kept = add_task(goals_client, title="Call the dentist")

    delete_goal(goals_client, goal["id"])

    assert is_gone(goals_client, goal["id"])
    week = goals_client.get(f"/api/weeks/{WEEK}").json()["tasks"]
    assert [task["id"] for task in week] == [kept["id"]]
    assert live_rows(connection, goal["id"]) == {}


def test_an_item_continued_from_it_stays_without_it(goals_client: TestClient) -> None:
    goal = create_goal(goals_client, lifting())
    goals_client.post(f"/api/goals/{goal['id']}/mark-reached")
    kept = create(
        goals_client,
        item(
            name="Lifting",
            schedule={"kind": "flexible", "times": 3, "period": "week"},
            fromGoalId=goal["id"],
        ),
    )

    delete_goal(goals_client, goal["id"])

    assert [(found["id"], found["fromGoalId"]) for found in listed(goals_client)] == [
        (kept["id"], None)
    ]


def test_deleting_twice_changes_nothing_more(
    goals_client: TestClient, connection: Connection
) -> None:
    goal = create_goal(goals_client, no_sugar())
    delete_goal(goals_client, goal["id"])

    assert delete_goal(goals_client, goal["id"]).status_code == 204
    assert [row.action for row in audit_rows(connection, goal["id"])] == [
        "create goal",
        "delete goal",
    ]


def test_another_users_goal_or_an_unknown_id_is_not_found(
    goals_client: TestClient, connection: Connection
) -> None:
    theirs = add_goal_for(connection, add_other_user(connection))

    assert delete_goal(goals_client, str(theirs)).status_code == 404
    assert delete_goal(goals_client, str(uuid4())).status_code == 404
