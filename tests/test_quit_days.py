"""A quitting goal's daily answer: answerQuitDay and clearQuitDay (spec `quitting-goals`)."""

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from tests.test_aspirations import add_other_user
from tests.test_goals import ZONE, create_goal, lifting, no_sugar

TODAY = "2026-11-18"  # the pinned Wednesday
YESTERDAY = "2026-11-17"


@pytest.fixture
def quit_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


@pytest.fixture
def goal_id(quit_client: TestClient) -> str:
    goal: dict[str, Any] = create_goal(quit_client, no_sugar(startDate="2026-11-01"))
    return str(goal["id"])


def answer(client: TestClient, goal_id: str, day: str, held: bool) -> Any:
    return client.put(f"/api/goals/{goal_id}/quit-days/{day}", json={"held": held})


def clear(client: TestClient, goal_id: str, day: str) -> Any:
    return client.post(f"/api/goals/{goal_id}/quit-days/{day}/clear")


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def live_rows(connection: Connection) -> list[Any]:
    return list(
        connection.execute(text("select day, held from quit_days where deleted_at is null"))
    )


def audit_count(connection: Connection) -> int:
    count: int = connection.execute(
        text("select count(*) from audit_log where table_name = 'quit_days'")
    ).scalar_one()
    return count


def test_a_day_is_answered(quit_client: TestClient, goal_id: str) -> None:
    assert ok(answer(quit_client, goal_id, TODAY, True)) == {
        "goalId": goal_id,
        "day": TODAY,
        "held": True,
        "urge": None,
    }


def test_an_answer_is_changed_and_cleared_keeping_one_row(
    quit_client: TestClient, goal_id: str, connection: Connection
) -> None:
    ok(answer(quit_client, goal_id, TODAY, True))
    assert ok(answer(quit_client, goal_id, TODAY, False))["held"] is False
    assert len(live_rows(connection)) == 1

    assert ok(clear(quit_client, goal_id, TODAY))["held"] is None
    assert live_rows(connection) == []

    ok(answer(quit_client, goal_id, TODAY, True))
    assert len(live_rows(connection)) == 1


def test_the_same_answer_twice_changes_nothing_more(
    quit_client: TestClient, goal_id: str, connection: Connection
) -> None:
    first = ok(answer(quit_client, goal_id, TODAY, True))
    count = audit_count(connection)

    assert ok(answer(quit_client, goal_id, TODAY, True)) == first
    assert audit_count(connection) == count


def test_clearing_twice_changes_nothing_more(
    quit_client: TestClient, goal_id: str, connection: Connection
) -> None:
    ok(answer(quit_client, goal_id, TODAY, True))
    ok(clear(quit_client, goal_id, TODAY))
    count = audit_count(connection)

    assert ok(clear(quit_client, goal_id, TODAY))["held"] is None
    assert audit_count(connection) == count


def test_an_unanswered_day_can_be_cleared(quit_client: TestClient, goal_id: str) -> None:
    assert ok(clear(quit_client, goal_id, YESTERDAY))["held"] is None


def test_a_day_a_week_old_can_still_be_answered(quit_client: TestClient, goal_id: str) -> None:
    assert ok(answer(quit_client, goal_id, "2026-11-11", True))["day"] == "2026-11-11"


def test_the_goals_first_day_can_be_answered(quit_client: TestClient, goal_id: str) -> None:
    ok(answer(quit_client, goal_id, "2026-11-01", False))


@pytest.mark.parametrize("day", ["2026-10-31", "2026-11-19"])
def test_a_day_before_the_start_or_after_today_is_refused(
    quit_client: TestClient, goal_id: str, day: str
) -> None:
    assert answer(quit_client, goal_id, day, True).status_code == 409
    assert clear(quit_client, goal_id, day).status_code == 409


def test_only_a_quitting_goal_is_answered(quit_client: TestClient) -> None:
    building = str(create_goal(quit_client, lifting())["id"])

    assert answer(quit_client, building, TODAY, True).status_code == 409
    assert clear(quit_client, building, TODAY).status_code == 409


def test_another_users_goal_is_not_found(quit_client: TestClient, connection: Connection) -> None:
    other = add_other_user(connection)
    theirs = uuid4()
    connection.execute(
        text(
            "insert into goals (id, user_id, type, label, measurable_line, start_date)"
            " values (:id, :user_id, 'quitting', 'Theirs', 'Done', '2026-11-01')"
        ),
        {"id": theirs, "user_id": other},
    )

    for goal in (str(theirs), str(uuid4())):
        assert answer(quit_client, goal, TODAY, True).status_code == 404
        assert clear(quit_client, goal, TODAY).status_code == 404


def test_the_phones_time_zone_is_needed(client: TestClient, goal_id: str) -> None:
    del client.headers["X-Time-Zone"]

    assert answer(client, goal_id, TODAY, True).status_code == 422


def test_an_answer_is_yes_or_no(quit_client: TestClient, goal_id: str) -> None:
    response = quit_client.put(f"/api/goals/{goal_id}/quit-days/{TODAY}", json={"held": None})

    assert response.status_code == 422


def test_a_paused_goal_can_still_be_answered(quit_client: TestClient, goal_id: str) -> None:
    ok(quit_client.post(f"/api/goals/{goal_id}/pause"))

    assert ok(answer(quit_client, goal_id, YESTERDAY, True))["held"] is True


def test_the_audit_log_names_each_action(
    quit_client: TestClient, goal_id: str, connection: Connection
) -> None:
    ok(answer(quit_client, goal_id, TODAY, True))
    ok(clear(quit_client, goal_id, TODAY))

    actions = [
        row.action
        for row in connection.execute(
            text("select action from audit_log where table_name = 'quit_days' order by id")
        )
    ]
    assert actions == ["answer quit day", "clear quit day"]
