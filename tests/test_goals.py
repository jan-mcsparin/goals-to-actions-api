from collections.abc import Iterator
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.config import FIXED_USER_ID
from app.weeks import week_of
from tests.test_aspirations import add_aspiration_for, add_other_user, audit_rows
from tests.test_aspirations import create as create_aspiration

ZONE = "America/Denver"


@pytest.fixture
def goals_client(client: TestClient) -> Iterator[TestClient]:
    """Every goal route needs the day, so every request sends the phone's time zone."""
    client.headers["X-Time-Zone"] = ZONE
    yield client


def today() -> date:
    return datetime.now(ZoneInfo(ZONE)).date()


def lifting(**changes: Any) -> dict[str, Any]:
    return {
        "type": "building",
        "label": "Be strong",
        "measurableLine": "Deadlift 1.5x bodyweight",
        "weeklyTarget": {"kind": "count", "sessions": 3, "unit": "lifting sessions"},
    } | changes


def no_sugar(**changes: Any) -> dict[str, Any]:
    return {"type": "quitting", "label": "No sugar", "measurableLine": "90 days clean"} | changes


def create_goal(client: TestClient, body: dict[str, Any], goal_id: UUID | None = None) -> Any:
    response = client.put(f"/api/goals/{goal_id or uuid4()}", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def add_goal_for(connection: Connection, user_id: UUID) -> UUID:
    goal_id = uuid4()
    connection.execute(
        text(
            "insert into goals (id, user_id, type, label, measurable_line, start_date)"
            " values (:id, :user_id, 'one_off', 'Theirs', 'Done', '2026-11-16')"
        ),
        {"id": goal_id, "user_id": user_id},
    )
    return goal_id


# createGoal


def test_create_returns_a_building_goal_with_its_first_target(goals_client: TestClient) -> None:
    aspiration = create_aspiration(goals_client, "Be fit")
    goal_id = uuid4()

    goal = create_goal(goals_client, lifting(aspirationId=aspiration["id"], baseline="1x"), goal_id)

    assert goal == {
        "id": str(goal_id),
        "aspirationId": aspiration["id"],
        "type": "building",
        "label": "Be strong",
        "measurableLine": "Deadlift 1.5x bodyweight",
        "baseline": "1x",
        "status": "active",
        "startDate": today().isoformat(),
        "deadline": None,
        "endedOn": None,
        "slipped": False,
        "weeklyTarget": {
            "kind": "count",
            "sessions": 3,
            "amount": None,
            "unit": "lifting sessions",
            "effectiveFrom": week_of(today()).isoformat(),
        },
        "createdAt": goal["createdAt"],
    }


def test_an_amount_target_keeps_its_amount(goals_client: TestClient) -> None:
    target = {"kind": "amount", "sessions": 4, "amount": 25.5, "unit": "miles"}

    goal = create_goal(goals_client, lifting(label="Run", weeklyTarget=target))

    assert goal["weeklyTarget"]["amount"] == 25.5


def test_quitting_and_one_off_goals_have_no_target(goals_client: TestClient) -> None:
    quitting = create_goal(goals_client, no_sugar(startDate="2026-11-01", deadline="2027-01-30"))
    one_off = create_goal(
        goals_client, {"type": "oneOff", "label": "Move house", "measurableLine": "Keys handed in"}
    )

    assert (quitting["type"], quitting["startDate"], quitting["deadline"]) == (
        "quitting",
        "2026-11-01",
        "2027-01-30",
    )
    assert quitting["weeklyTarget"] is None
    assert (one_off["type"], one_off["weeklyTarget"]) == ("oneOff", None)


@pytest.mark.parametrize(
    "body",
    [
        lifting(weeklyTarget=None),
        no_sugar(weeklyTarget={"kind": "count", "sessions": 3, "unit": "days"}),
        lifting(weeklyTarget={"kind": "count", "sessions": 3, "amount": 5, "unit": "x"}),
        lifting(weeklyTarget={"kind": "amount", "sessions": 3, "unit": "miles"}),
        lifting(weeklyTarget={"kind": "count", "sessions": 0, "unit": "x"}),
        lifting(label="  "),
        lifting(measurableLine=""),
        lifting(type="habit"),
        lifting(startDate="2026-11-16", deadline="2026-11-15"),
        lifting(label="nul\x00"),
    ],
)
def test_a_body_that_breaks_the_rules_is_refused(goals_client: TestClient, body: Any) -> None:
    response = goals_client.put(f"/api/goals/{uuid4()}", json=body)

    assert response.status_code == 422


def test_a_deadline_before_today_with_no_start_date_is_refused(goals_client: TestClient) -> None:
    yesterday = (today() - timedelta(days=1)).isoformat()

    response = goals_client.put(f"/api/goals/{uuid4()}", json=lifting(deadline=yesterday))

    assert response.status_code == 409


def test_the_same_create_twice_returns_the_goal_as_it_is(
    goals_client: TestClient, connection: Connection
) -> None:
    goal_id = uuid4()
    first = create_goal(goals_client, lifting(), goal_id)

    again = create_goal(goals_client, lifting(label="Be stronger"), goal_id)

    assert again == first
    assert [row.action for row in audit_rows(connection, goal_id)] == ["create goal"]


def test_a_goal_under_another_users_aspiration_is_not_found(
    goals_client: TestClient, connection: Connection
) -> None:
    theirs = add_aspiration_for(connection, add_other_user(connection), "Theirs")

    response = goals_client.put(f"/api/goals/{uuid4()}", json=lifting(aspirationId=str(theirs)))

    assert response.status_code == 404


def test_a_goal_under_a_retired_aspiration_is_not_allowed(goals_client: TestClient) -> None:
    aspiration = create_aspiration(goals_client, "Sail")
    goals_client.post(f"/api/aspirations/{aspiration['id']}/retire", json={"itsWork": "keep"})

    response = goals_client.put(
        f"/api/goals/{uuid4()}", json=lifting(aspirationId=aspiration["id"])
    )

    assert response.status_code == 409


def test_an_id_already_another_users_is_not_allowed(
    goals_client: TestClient, connection: Connection
) -> None:
    theirs = add_goal_for(connection, add_other_user(connection))

    response = goals_client.put(f"/api/goals/{theirs}", json=lifting())

    assert response.status_code == 409


def test_once_next_week_is_open_the_first_target_starts_next_week(
    goals_client: TestClient, connection: Connection
) -> None:
    next_week = week_of(today()) + timedelta(weeks=1)
    connection.execute(
        text("update users set planned_through_week = :week where id = :id"),
        {"week": next_week, "id": FIXED_USER_ID},
    )

    goal = create_goal(goals_client, lifting())

    assert goal["weeklyTarget"]["effectiveFrom"] == next_week.isoformat()


def test_create_needs_the_time_zone(client: TestClient) -> None:
    response = client.put(f"/api/goals/{uuid4()}", json=lifting())

    assert response.status_code == 422


# getGoal and listGoals


def test_get_returns_the_goal(goals_client: TestClient) -> None:
    goal = create_goal(goals_client, lifting())

    response = goals_client.get(f"/api/goals/{goal['id']}")

    assert response.json() == goal


def test_get_of_another_users_goal_or_an_unknown_id_is_not_found(
    goals_client: TestClient, connection: Connection
) -> None:
    theirs = add_goal_for(connection, add_other_user(connection))

    assert goals_client.get(f"/api/goals/{theirs}").status_code == 404
    assert goals_client.get(f"/api/goals/{uuid4()}").status_code == 404


def test_an_active_goal_past_its_deadline_has_slipped(goals_client: TestClient) -> None:
    start = (today() - timedelta(days=30)).isoformat()
    yesterday = (today() - timedelta(days=1)).isoformat()

    slipped = create_goal(goals_client, no_sugar(startDate=start, deadline=yesterday))
    due_today = create_goal(goals_client, no_sugar(deadline=today().isoformat()))

    assert slipped["slipped"] is True
    assert due_today["slipped"] is False


def test_list_orders_goals_by_their_aspirations(
    goals_client: TestClient, connection: Connection
) -> None:
    first = create_aspiration(goals_client, "First")
    second = create_aspiration(goals_client, "Second")
    retired = create_aspiration(goals_client, "Retired")
    goals_client.post(f"/api/aspirations/{retired['id']}/retire", json={"itsWork": "keep"})
    add_goal_for(connection, add_other_user(connection))

    under_retired = create_goal(goals_client, no_sugar(label="Under retired"))
    under_second = create_goal(goals_client, lifting(label="B", aspirationId=second["id"]))
    under_first = create_goal(goals_client, lifting(label="A1", aspirationId=first["id"]))
    under_first_later = create_goal(goals_client, no_sugar(label="A2", aspirationId=first["id"]))
    connection.execute(
        text("update goals set aspiration_id = :aspiration where id = :id"),
        {"aspiration": retired["id"], "id": under_retired["id"]},
    )
    # One test is one transaction, so every row has the same created_at until it's spread out.
    connection.execute(
        text("update goals set created_at = created_at + interval '1 minute' where id = :id"),
        {"id": under_first_later["id"]},
    )
    no_aspiration = create_goal(goals_client, no_sugar(label="Loose"))

    listed = goals_client.get("/api/goals").json()["goals"]

    assert [goal["label"] for goal in listed] == [
        under_first["label"],
        under_first_later["label"],
        under_second["label"],
        under_retired["label"],
        no_aspiration["label"],
    ]
    assert listed[0] == under_first
