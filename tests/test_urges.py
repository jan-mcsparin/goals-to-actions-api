"""The urge rating beside a quitting goal's day: rateUrge and clearUrgeRating."""

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from tests.test_aspirations import add_other_user
from tests.test_goals import ZONE, create_goal, lifting, no_sugar
from tests.test_quit_days import TODAY, YESTERDAY, answer, ok


@pytest.fixture
def quit_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


@pytest.fixture
def goal_id(quit_client: TestClient) -> str:
    return str(create_goal(quit_client, no_sugar(startDate="2026-11-01"))["id"])


def rate(client: TestClient, goal_id: str, day: str, level: str) -> Any:
    return client.put(f"/api/goals/{goal_id}/urges/{day}", json={"level": level})


def clear(client: TestClient, goal_id: str, day: str) -> Any:
    return client.post(f"/api/goals/{goal_id}/urges/{day}/clear")


def live_ratings(connection: Connection) -> list[Any]:
    return list(connection.execute(text("select level from urge_ratings where deleted_at is null")))


def test_an_urge_is_rated_changed_and_cleared(
    quit_client: TestClient, goal_id: str, connection: Connection
) -> None:
    assert ok(rate(quit_client, goal_id, TODAY, "low")) == {
        "goalId": goal_id,
        "day": TODAY,
        "held": None,
        "urge": "low",
    }
    assert ok(rate(quit_client, goal_id, TODAY, "strong"))["urge"] == "strong"
    assert len(live_ratings(connection)) == 1

    assert ok(clear(quit_client, goal_id, TODAY))["urge"] is None
    assert ok(clear(quit_client, goal_id, TODAY))["urge"] is None
    assert live_ratings(connection) == []


def test_the_same_rating_twice_changes_nothing_more(
    quit_client: TestClient, goal_id: str, connection: Connection
) -> None:
    ok(rate(quit_client, goal_id, TODAY, "some"))
    count = connection.execute(text("select count(*) from audit_log")).scalar_one()

    ok(rate(quit_client, goal_id, TODAY, "some"))

    assert connection.execute(text("select count(*) from audit_log")).scalar_one() == count


def test_rating_the_urge_keeps_the_answer_and_the_other_way_round(
    quit_client: TestClient, goal_id: str
) -> None:
    ok(answer(quit_client, goal_id, YESTERDAY, True))

    assert ok(rate(quit_client, goal_id, YESTERDAY, "some"))["held"] is True
    assert ok(answer(quit_client, goal_id, YESTERDAY, False))["urge"] == "some"
    assert ok(clear(quit_client, goal_id, YESTERDAY))["held"] is False


@pytest.mark.parametrize("day", ["2026-10-31", "2026-11-19"])
def test_a_day_before_the_start_or_after_today_is_refused(
    quit_client: TestClient, goal_id: str, day: str
) -> None:
    assert rate(quit_client, goal_id, day, "low").status_code == 409
    assert clear(quit_client, goal_id, day).status_code == 409


def test_only_a_quitting_goal_is_rated(quit_client: TestClient) -> None:
    building = str(create_goal(quit_client, lifting())["id"])

    assert rate(quit_client, building, TODAY, "low").status_code == 409


def test_another_users_goal_is_not_found(quit_client: TestClient, connection: Connection) -> None:
    theirs = uuid4()
    connection.execute(
        text(
            "insert into goals (id, user_id, type, label, measurable_line, start_date)"
            " values (:id, :user_id, 'quitting', 'Theirs', 'Done', '2026-11-01')"
        ),
        {"id": theirs, "user_id": add_other_user(connection)},
    )

    assert rate(quit_client, str(theirs), TODAY, "low").status_code == 404
    assert clear(quit_client, str(theirs), TODAY).status_code == 404


def test_an_urge_is_low_some_or_strong(quit_client: TestClient, goal_id: str) -> None:
    assert rate(quit_client, goal_id, TODAY, "none").status_code == 422


def test_the_audit_log_names_each_action(
    quit_client: TestClient, goal_id: str, connection: Connection
) -> None:
    ok(rate(quit_client, goal_id, TODAY, "low"))
    ok(clear(quit_client, goal_id, TODAY))

    actions = [
        row.action
        for row in connection.execute(
            text("select action from audit_log where table_name = 'urge_ratings' order by id")
        )
    ]
    assert actions == ["rate urge", "clear urge rating"]
