from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from tests.test_aspirations import add_other_user
from tests.test_goals import ZONE, add_goal_for, create_goal, lifting, no_sugar, today
from tests.test_milestones import add_milestone, page


@pytest.fixture
def goals_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


def check_in(
    client: TestClient,
    goal_id: str,
    milestone_id: str | None,
    outcome: str = "hit",
    result: str | None = None,
    check_in_id: UUID | None = None,
) -> Any:
    return client.put(
        f"/api/check-ins/{check_in_id or uuid4()}",
        json={
            "goalId": goal_id,
            "milestoneId": milestone_id,
            "outcome": outcome,
            "result": result,
        },
    )


def goal_with_milestones(client: TestClient, count: int, **changes: Any) -> Any:
    goal = create_goal(client, lifting(**changes))
    for number in range(1, count + 1):
        add_milestone(client, goal["id"], f"M{number}")
    return page(client, goal["id"])


def history(connection: Connection) -> set[tuple[str | None, str, str | None]]:
    """The check-ins kept, dated today. A set: one test is one transaction, so every row has
    the same created_at and there's no order to read."""
    rows = connection.execute(
        text("select milestone_id, outcome, result, checked_in_on from check_ins")
    )
    return {
        (row.milestone_id and str(row.milestone_id), row.outcome, row.result)
        for row in rows
        if row.checked_in_on == today()
    }


def statuses(goal_page: Any) -> list[str]:
    return [m["status"] for m in goal_page["milestones"]]


def test_a_hit_on_next_marks_it_hit_and_moves_next_on(
    goals_client: TestClient, connection: Connection
) -> None:
    before = goal_with_milestones(goals_client, 2)
    first, second = (m["id"] for m in before["milestones"])

    response = check_in(goals_client, before["goal"]["id"], first, "hit", " 155 ")

    assert response.status_code == 200, response.text
    after = response.json()
    assert statuses(after) == ["hit", "upcoming"]
    assert after["progress"] == {"hit": 1, "of": 3}
    assert after["latest"] == {"result": "155", "checkedInOn": today().isoformat()}
    assert history(connection) == {(first, "hit", "155")}
    assert check_in(goals_client, before["goal"]["id"], second).status_code == 200


def test_a_not_yet_stays_next_and_every_check_in_is_kept(
    goals_client: TestClient, connection: Connection
) -> None:
    before = goal_with_milestones(goals_client, 2)
    goal_id = before["goal"]["id"]
    first, second = (m["id"] for m in before["milestones"])

    not_yet = check_in(goals_client, goal_id, first, "notYet", "140").json()
    passed_over = check_in(goals_client, goal_id, second)
    check_in(goals_client, goal_id, first, "hit", "155")

    assert statuses(not_yet) == ["notYet", "upcoming"]
    assert passed_over.status_code == 409
    assert history(connection) == {(first, "not_yet", "140"), (first, "hit", "155")}


def test_a_hit_on_the_goals_own_line_marks_it_reached(goals_client: TestClient) -> None:
    before = goal_with_milestones(goals_client, 1)
    goal_id = before["goal"]["id"]
    check_in(goals_client, goal_id, before["milestones"][0]["id"])

    after = check_in(goals_client, goal_id, None, "hit", "Deadlift 1.5x").json()

    assert after["goal"]["status"] == "reached"
    assert after["goal"]["endedOn"] == today().isoformat()
    assert after["progress"] == {"hit": 2, "of": 2}


def test_a_not_yet_on_the_goals_own_line_only_adds_to_the_history(
    goals_client: TestClient, connection: Connection
) -> None:
    goal = create_goal(goals_client, no_sugar())

    after = check_in(goals_client, goal["id"], None, "notYet", "Day 40").json()

    assert after["goal"] == goal
    assert after["progress"] == {"hit": 0, "of": 1}
    assert history(connection) == {(None, "not_yet", "Day 40")}


def test_the_goals_own_line_is_next_only_once_every_milestone_is_hit(
    goals_client: TestClient,
) -> None:
    before = goal_with_milestones(goals_client, 1)

    assert check_in(goals_client, before["goal"]["id"], None).status_code == 409


def test_a_milestone_that_is_already_hit_is_not_next(goals_client: TestClient) -> None:
    before = goal_with_milestones(goals_client, 2)
    first = before["milestones"][0]["id"]
    check_in(goals_client, before["goal"]["id"], first)

    assert check_in(goals_client, before["goal"]["id"], first).status_code == 409


@pytest.mark.parametrize(("status", "code"), [("paused", 200), ("reached", 409), ("ended", 409)])
def test_check_in_needs_an_active_or_paused_goal(
    goals_client: TestClient, status: str, code: int
) -> None:
    goal = create_goal(goals_client, lifting())
    route = {"paused": "pause", "reached": "mark-reached", "ended": "end"}[status]
    goals_client.post(f"/api/goals/{goal['id']}/{route}")

    assert check_in(goals_client, goal["id"], None, "notYet").status_code == code


def test_a_one_off_goal_has_no_check_ins(goals_client: TestClient) -> None:
    goal = create_goal(goals_client, no_sugar(type="oneOff"))

    assert check_in(goals_client, goal["id"], None).status_code == 409


def test_another_users_goal_is_not_found(goals_client: TestClient, connection: Connection) -> None:
    theirs = add_goal_for(connection, add_other_user(connection))

    assert check_in(goals_client, str(theirs), None).status_code == 404
    assert check_in(goals_client, str(uuid4()), None).status_code == 404


def test_the_same_check_in_twice_is_kept_once(
    goals_client: TestClient, connection: Connection
) -> None:
    before = goal_with_milestones(goals_client, 2)
    first = before["milestones"][0]["id"]
    check_in_id = uuid4()
    once = check_in(goals_client, before["goal"]["id"], first, "notYet", "140", check_in_id)

    twice = check_in(goals_client, before["goal"]["id"], first, "notYet", "140", check_in_id)

    assert twice.status_code == 200
    assert twice.json() == once.json()
    assert len(history(connection)) == 1


def test_an_id_already_another_goals_check_in_is_not_allowed(
    goals_client: TestClient, connection: Connection
) -> None:
    first = create_goal(goals_client, no_sugar())
    second = create_goal(goals_client, no_sugar())
    check_in_id = uuid4()
    check_in(goals_client, first["id"], None, "notYet", "Day 3", check_in_id)

    response = check_in(goals_client, second["id"], None, "notYet", "Day 3", check_in_id)

    assert response.status_code == 409
    assert history(connection) == {(None, "not_yet", "Day 3")}


def test_latest_is_the_newest_check_in_with_a_result(
    goals_client: TestClient, connection: Connection
) -> None:
    before = goal_with_milestones(goals_client, 2)
    goal_id = before["goal"]["id"]
    first, second = (m["id"] for m in before["milestones"])
    check_in(goals_client, goal_id, first, "notYet", "140")
    # One test is one transaction: spread the moments so "newest" means something.
    connection.execute(text("update check_ins set created_at = created_at - interval '1 hour'"))
    check_in(goals_client, goal_id, first, "hit", "155")
    connection.execute(
        text("update check_ins set created_at = created_at - interval '1 minute'"
             " where result = '155'")
    )  # fmt: skip
    check_in(goals_client, goal_id, second, "notYet")

    assert page(goals_client, goal_id)["latest"]["result"] == "155"


@pytest.mark.parametrize(
    "body",
    [
        {"outcome": "missed"},
        {"result": "x" * 501},
        {"result": "nul\x00"},
        {"outcome": None},
    ],
)
def test_a_check_in_that_breaks_the_rules_is_refused(
    goals_client: TestClient, body: dict[str, Any]
) -> None:
    goal = create_goal(goals_client, no_sugar())
    request = {"goalId": goal["id"], "milestoneId": None, "outcome": "hit"} | body

    response = goals_client.put(f"/api/check-ins/{uuid4()}", json=request)

    assert response.status_code == 422


# keepMilestone


def keep(client: TestClient, milestone_id: str) -> Any:
    return client.post(f"/api/milestones/{milestone_id}/keep")


def test_keep_puts_a_not_yet_back_to_upcoming_and_leaves_the_history(
    goals_client: TestClient, connection: Connection
) -> None:
    before = goal_with_milestones(goals_client, 1)
    first = before["milestones"][0]
    check_in(goals_client, before["goal"]["id"], first["id"], "notYet", "140")

    response = keep(goals_client, first["id"])

    assert response.status_code == 200, response.text
    assert response.json()["milestones"] == [first]
    assert history(connection) == {(first["id"], "not_yet", "140")}


def test_keep_on_an_upcoming_milestone_changes_nothing(
    goals_client: TestClient, connection: Connection
) -> None:
    before = goal_with_milestones(goals_client, 1)
    first = before["milestones"][0]
    audited = connection.execute(text("select count(*) from audit_log")).scalar()

    assert keep(goals_client, first["id"]).json() == before
    assert connection.execute(text("select count(*) from audit_log")).scalar() == audited


def test_keep_on_a_hit_milestone_is_not_allowed(goals_client: TestClient) -> None:
    before = goal_with_milestones(goals_client, 1)
    first = before["milestones"][0]["id"]
    check_in(goals_client, before["goal"]["id"], first)

    assert keep(goals_client, first).status_code == 409


def test_keep_of_an_unknown_milestone_is_not_found(goals_client: TestClient) -> None:
    assert keep(goals_client, str(uuid4())).status_code == 404
