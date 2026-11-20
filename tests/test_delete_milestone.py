"""Deleting a milestone made by mistake (spec `delete`): its check-ins go with it, and the
ones after it move up."""

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from tests.test_aspirations import add_other_user, audit_rows
from tests.test_check_ins import check_in
from tests.test_goals import ZONE, add_goal_for, create_goal, lifting
from tests.test_milestones import add_milestone, lines, page


@pytest.fixture
def goals_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


def delete_milestone(client: TestClient, milestone_id: str) -> Any:
    return client.delete(f"/api/milestones/{milestone_id}")


def goal_with_three(client: TestClient) -> tuple[str, list[str]]:
    goal = create_goal(client, lifting())
    for line in ("Bench 135", "Bench 145", "Bench 155"):
        add_milestone(client, goal["id"], line)
    return goal["id"], [m["id"] for m in page(client, goal["id"])["milestones"]]


def test_the_ones_after_it_move_up_and_a_new_one_goes_last(goals_client: TestClient) -> None:
    goal_id, (_, second, _) = goal_with_three(goals_client)

    response = delete_milestone(goals_client, second)

    assert response.status_code == 200
    assert lines(response.json()) == [(1, "Bench 135"), (2, "Bench 155")]
    add_milestone(goals_client, goal_id, "Bench 165")
    assert lines(page(goals_client, goal_id))[-1] == (3, "Bench 165")


def test_its_check_ins_go_with_it(goals_client: TestClient) -> None:
    goal_id, (first, _, _) = goal_with_three(goals_client)
    assert check_in(goals_client, goal_id, first, result="Bench 137").status_code == 200

    goal_page = delete_milestone(goals_client, first).json()

    assert goal_page["latest"] is None
    assert goal_page["progress"] == {"hit": 0, "of": 3}
    assert [m["status"] for m in goal_page["milestones"]] == ["upcoming", "upcoming"]


def test_deleting_twice_returns_the_page_again(
    goals_client: TestClient, connection: Connection
) -> None:
    goal_id, (first, _, _) = goal_with_three(goals_client)
    once = delete_milestone(goals_client, first).json()

    again = delete_milestone(goals_client, first)

    assert again.status_code == 200
    assert again.json() == once
    assert [row.action for row in audit_rows(connection, first)][-1] == "delete milestone"
    assert len(audit_rows(connection, first)) == 2


def test_another_users_milestone_or_an_unknown_id_is_not_found(
    goals_client: TestClient, connection: Connection
) -> None:
    other_user = add_other_user(connection)
    theirs = add_goal_for(connection, other_user)
    connection.execute(text("update goals set type = 'building' where id = :id"), {"id": theirs})
    their_milestone = uuid4()
    connection.execute(
        text(
            "insert into milestones (id, user_id, goal_id, goal_type, position, measurable_line)"
            " values (:id, :user_id, :goal_id, 'building', 1, 'Theirs')"
        ),
        {"id": their_milestone, "user_id": other_user, "goal_id": theirs},
    )

    assert delete_milestone(goals_client, str(their_milestone)).status_code == 404
    assert delete_milestone(goals_client, str(uuid4())).status_code == 404
