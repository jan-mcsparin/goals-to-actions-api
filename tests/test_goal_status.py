from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from tests.test_aspirations import add_other_user, audit_rows
from tests.test_aspirations import create as create_aspiration
from tests.test_goals import ZONE, add_goal_for, create_goal, lifting, today

STATUSES = ["active", "paused", "reached", "ended"]

# Each route: the statuses it is allowed from, and the status it leaves.
CHANGES = {
    "pause": ({"active"}, "paused"),
    "resume": ({"paused"}, "active"),
    "end": ({"active", "paused"}, "ended"),
    "mark-reached": ({"active", "paused"}, "reached"),
    "reopen": ({"reached"}, "active"),
    "go-again": ({"ended"}, "active"),
}
ACTIONS = {
    "pause": "pause goal",
    "resume": "resume goal",
    "end": "end goal",
    "mark-reached": "mark goal reached",
    "reopen": "reopen goal",
    "go-again": "go again",
}


@pytest.fixture
def goals_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


def goal_in(client: TestClient, connection: Connection, status: str, **changes: Any) -> Any:
    goal = create_goal(client, lifting(**changes))
    ended_on = today() if status in ("reached", "ended") else None
    connection.execute(
        text("update goals set status = :status, ended_on = :ended_on where id = :id"),
        {"status": status, "ended_on": ended_on, "id": goal["id"]},
    )
    return goal


def change(client: TestClient, goal_id: str, route: str) -> Any:
    return client.post(f"/api/goals/{goal_id}/{route}")


@pytest.mark.parametrize("route", CHANGES)
@pytest.mark.parametrize("status", STATUSES)
def test_each_change_from_each_status(
    goals_client: TestClient, connection: Connection, route: str, status: str
) -> None:
    allowed_from, leaves = CHANGES[route]
    goal = goal_in(goals_client, connection, status)
    audited_before = len(audit_rows(connection, goal["id"]))

    response = change(goals_client, goal["id"], route)

    if status in allowed_from:
        assert response.status_code == 200, response.text
        changed = response.json()
        assert changed["status"] == leaves
        ended = leaves in ("reached", "ended")
        assert changed["endedOn"] == (today().isoformat() if ended else None)
        assert [row.action for row in audit_rows(connection, goal["id"])][-1] == ACTIONS[route]
    elif status == leaves:
        assert response.status_code == 200, response.text
        assert response.json()["status"] == status
        assert len(audit_rows(connection, goal["id"])) == audited_before
    else:
        assert response.status_code == 409


@pytest.mark.parametrize("route", ["resume", "reopen", "go-again"])
def test_coming_back_works_under_a_retired_aspiration(
    goals_client: TestClient, connection: Connection, route: str
) -> None:
    aspiration = create_aspiration(goals_client, "Sail")
    status = {"resume": "paused", "reopen": "reached", "go-again": "ended"}[route]
    goal = goal_in(goals_client, connection, status, aspirationId=aspiration["id"])
    goals_client.post(f"/api/aspirations/{aspiration['id']}/retire", json={"itsWork": "keep"})

    response = change(goals_client, goal["id"], route)

    assert response.status_code == 200, response.text
    assert response.json()["aspirationId"] == aspiration["id"]


def test_go_again_keeps_the_target_as_it_was(
    goals_client: TestClient, connection: Connection
) -> None:
    goal = goal_in(goals_client, connection, "active")
    change(goals_client, goal["id"], "end")

    again = change(goals_client, goal["id"], "go-again").json()

    assert again["weeklyTarget"] == goal["weeklyTarget"]


@pytest.mark.parametrize("route", CHANGES)
def test_another_users_goal_is_not_found(
    goals_client: TestClient, connection: Connection, route: str
) -> None:
    theirs = add_goal_for(connection, add_other_user(connection))

    assert change(goals_client, str(theirs), route).status_code == 404
    assert change(goals_client, str(uuid4()), route).status_code == 404
