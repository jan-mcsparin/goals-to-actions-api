"""What the front end's setup screens read: each listed goal's progress, and the goal page's
aspiration and milestone results."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from tests.test_aspirations import add_other_user
from tests.test_aspirations import create as create_aspiration
from tests.test_check_ins import check_in, goal_with_milestones
from tests.test_goals import ZONE, add_goal_for, create_goal, lifting, no_sugar
from tests.test_milestones import add_milestone, page


@pytest.fixture
def goals_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


def listed_progress(client: TestClient) -> dict[str, Any]:
    return {goal["id"]: goal["progress"] for goal in client.get("/api/goals").json()["goals"]}


# listGoals


def test_each_listed_goal_carries_the_progress_its_page_reads(
    goals_client: TestClient, connection: Connection
) -> None:
    add_goal_for(connection, add_other_user(connection))
    none = create_goal(goals_client, no_sugar())
    some_hit = goal_with_milestones(goals_client, 3)["goal"]
    check_in(
        goals_client, some_hit["id"], page(goals_client, some_hit["id"])["milestones"][0]["id"]
    )
    reached = goal_with_milestones(goals_client, 2)["goal"]
    goals_client.post(f"/api/goals/{reached['id']}/mark-reached")
    with_a_deleted = goal_with_milestones(goals_client, 2)["goal"]
    connection.execute(
        text("update milestones set deleted_at = now() where goal_id = :goal and position = 2"),
        {"goal": with_a_deleted["id"]},
    )

    progress = listed_progress(goals_client)

    assert progress == {
        none["id"]: {"hit": 0, "of": 1},
        some_hit["id"]: {"hit": 1, "of": 4},
        reached["id"]: {"hit": 3, "of": 3},
        with_a_deleted["id"]: {"hit": 0, "of": 2},
    }
    for goal_id, listed in progress.items():
        assert page(goals_client, goal_id)["progress"] == listed


# The goal's page


def test_a_reached_goal_counts_complete(goals_client: TestClient) -> None:
    """Milestones never checked in were passed on the way (flows.md, decided Nov 11)."""
    goal = goal_with_milestones(goals_client, 2)["goal"]
    check_in(goals_client, goal["id"], page(goals_client, goal["id"])["milestones"][0]["id"])

    goals_client.post(f"/api/goals/{goal['id']}/mark-reached")

    assert page(goals_client, goal["id"])["progress"] == {"hit": 3, "of": 3}


def test_the_goal_page_names_its_aspiration(goals_client: TestClient) -> None:
    be_strong = create_aspiration(goals_client, "Be strong")
    retired = create_aspiration(goals_client, "Retired")
    under = create_goal(goals_client, lifting(aspirationId=be_strong["id"]))
    under_retired = create_goal(goals_client, lifting(aspirationId=retired["id"]))
    goals_client.post(f"/api/aspirations/{retired['id']}/retire", json={"itsWork": "keep"})
    loose = create_goal(goals_client, no_sugar())

    assert page(goals_client, under["id"])["aspiration"] == {
        "id": be_strong["id"],
        "name": "Be strong",
    }
    assert page(goals_client, under_retired["id"])["aspiration"] == {
        "id": retired["id"],
        "name": "Retired",
    }
    assert page(goals_client, loose["id"])["aspiration"] is None


def test_a_milestone_write_returns_the_aspiration_too(goals_client: TestClient) -> None:
    be_strong = create_aspiration(goals_client, "Be strong")
    goal = create_goal(goals_client, lifting(aspirationId=be_strong["id"]))

    response = add_milestone(goals_client, goal["id"])

    assert response.json()["aspiration"] == {"id": be_strong["id"], "name": "Be strong"}


def test_each_checked_in_milestone_carries_its_latest_result(goals_client: TestClient) -> None:
    """ "Hit · 155" and "Not yet · 160" on the timeline, and "Now: 160" on the not-yet card."""
    before = goal_with_milestones(goals_client, 4)
    goal_id = before["goal"]["id"]
    first, second, third, _ = (m["id"] for m in before["milestones"])
    check_in(goals_client, goal_id, first, "notYet", "150")
    check_in(goals_client, goal_id, first, "hit", "155")
    check_in(goals_client, goal_id, second, "notYet", "158")
    check_in(goals_client, goal_id, second, "hit")
    check_in(goals_client, goal_id, third, "notYet", "160")

    after = page(goals_client, goal_id)

    assert [(m["status"], m["result"]) for m in after["milestones"]] == [
        ("hit", "155"),
        ("hit", None),
        ("notYet", "160"),
        ("upcoming", None),
    ]


def test_a_kept_milestone_is_upcoming_with_no_result(goals_client: TestClient) -> None:
    before = goal_with_milestones(goals_client, 2)
    goal_id = before["goal"]["id"]
    first = before["milestones"][0]["id"]
    check_in(goals_client, goal_id, first, "notYet", "150")

    goals_client.post(f"/api/milestones/{first}/keep")

    assert page(goals_client, goal_id)["milestones"][0]["result"] is None
