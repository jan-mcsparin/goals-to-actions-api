from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from tests.test_aspirations import add_other_user, audit_rows
from tests.test_goals import ZONE, add_goal_for, create_goal, lifting, no_sugar, today


@pytest.fixture
def goals_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


def day(days_from_today: int) -> str:
    return (today() + timedelta(days=days_from_today)).isoformat()


def add_milestone(
    client: TestClient,
    goal_id: str,
    line: str = "Bench 155",
    target_date: str | None = None,
    milestone_id: UUID | None = None,
) -> Any:
    return client.put(
        f"/api/milestones/{milestone_id or uuid4()}",
        json={"goalId": goal_id, "measurableLine": line, "targetDate": target_date},
    )


def page(client: TestClient, goal_id: str) -> Any:
    response = client.get(f"/api/goals/{goal_id}")
    assert response.status_code == 200, response.text
    return response.json()


def lines(goal_page: Any) -> list[tuple[int, str]]:
    return [(m["position"], m["measurableLine"]) for m in goal_page["milestones"]]


# The goal's page


def test_a_goal_with_no_milestones_reads_0_of_1(goals_client: TestClient) -> None:
    goal = create_goal(goals_client, lifting())

    assert page(goals_client, goal["id"]) == {
        "goal": goal,
        "milestones": [],
        "progress": {"hit": 0, "of": 1},
        "latest": None,
    }


# addMilestone


def test_add_puts_the_milestone_last_and_returns_the_page(goals_client: TestClient) -> None:
    goal = create_goal(goals_client, lifting(deadline=day(90)))
    milestone_id = uuid4()
    add_milestone(goals_client, goal["id"], "Bench 135")

    response = add_milestone(goals_client, goal["id"], " Bench 155 ", day(30), milestone_id)

    assert response.status_code == 200, response.text
    added = response.json()
    assert added == page(goals_client, goal["id"])
    assert added["milestones"][1] == {
        "id": str(milestone_id),
        "position": 2,
        "measurableLine": "Bench 155",
        "targetDate": day(30),
        "status": "upcoming",
    }
    assert added["progress"] == {"hit": 0, "of": 3}


def test_a_quitting_goal_has_milestones(goals_client: TestClient) -> None:
    goal = create_goal(goals_client, no_sugar())

    assert add_milestone(goals_client, goal["id"], "30 days").status_code == 200


def test_a_one_off_goal_has_no_milestones(goals_client: TestClient) -> None:
    goal = create_goal(goals_client, no_sugar(type="oneOff"))

    assert add_milestone(goals_client, goal["id"]).status_code == 409


def test_the_same_add_twice_returns_the_page_as_it_is(
    goals_client: TestClient, connection: Connection
) -> None:
    goal = create_goal(goals_client, lifting())
    milestone_id = uuid4()
    first = add_milestone(goals_client, goal["id"], milestone_id=milestone_id).json()

    again = add_milestone(goals_client, goal["id"], "Other", milestone_id=milestone_id).json()

    assert again == first
    assert [row.action for row in audit_rows(connection, milestone_id)] == ["add milestone"]


@pytest.mark.parametrize(
    ("deadline", "target_date"),
    [(None, -1), (60, 61)],
)
def test_a_date_outside_the_goals_start_and_deadline_is_not_allowed(
    goals_client: TestClient, deadline: int | None, target_date: int
) -> None:
    goal = create_goal(goals_client, lifting(deadline=None if deadline is None else day(deadline)))

    response = add_milestone(goals_client, goal["id"], target_date=day(target_date))

    assert response.status_code == 409


def test_dates_on_the_start_and_the_deadline_are_allowed(goals_client: TestClient) -> None:
    goal = create_goal(goals_client, lifting(deadline=day(60)))

    assert add_milestone(goals_client, goal["id"], target_date=day(0)).status_code == 200
    assert add_milestone(goals_client, goal["id"], target_date=day(60)).status_code == 200


def test_another_users_goal_is_not_found(goals_client: TestClient, connection: Connection) -> None:
    theirs = add_goal_for(connection, add_other_user(connection))
    connection.execute(text("update goals set type = 'building' where id = :id"), {"id": theirs})

    assert add_milestone(goals_client, str(theirs)).status_code == 404
    assert add_milestone(goals_client, str(uuid4())).status_code == 404


def test_an_id_already_another_goals_milestone_is_not_allowed(goals_client: TestClient) -> None:
    first = create_goal(goals_client, lifting())
    second = create_goal(goals_client, lifting())
    milestone_id = uuid4()
    add_milestone(goals_client, first["id"], milestone_id=milestone_id)

    response = add_milestone(goals_client, second["id"], milestone_id=milestone_id)

    assert response.status_code == 409


@pytest.mark.parametrize("line", ["", "  ", "nul\x00", "x" * 501])
def test_a_line_that_breaks_the_rules_is_refused(goals_client: TestClient, line: str) -> None:
    goal = create_goal(goals_client, lifting())

    assert add_milestone(goals_client, goal["id"], line).status_code == 422
