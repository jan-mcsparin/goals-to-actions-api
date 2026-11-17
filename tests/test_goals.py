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


# updateGoal


def edit(**changes: Any) -> dict[str, Any]:
    return {
        "label": "Be stronger",
        "measurableLine": "Deadlift 2x bodyweight",
        "baseline": None,
        "aspirationId": None,
        "deadline": None,
    } | changes


def update_goal(client: TestClient, goal_id: str, body: dict[str, Any]) -> Any:
    return client.patch(f"/api/goals/{goal_id}", json=body)


def test_update_changes_the_fields_sent(goals_client: TestClient) -> None:
    aspiration = create_aspiration(goals_client, "Be fit")
    goal = create_goal(goals_client, lifting(baseline="1x"))
    deadline = (today() + timedelta(days=60)).isoformat()

    response = update_goal(
        goals_client,
        goal["id"],
        edit(baseline=" 1.2x ", aspirationId=aspiration["id"], deadline=deadline),
    )

    assert response.status_code == 200, response.text
    assert response.json() == goal | {
        "label": "Be stronger",
        "measurableLine": "Deadlift 2x bodyweight",
        "baseline": "1.2x",
        "aspirationId": aspiration["id"],
        "deadline": deadline,
    }


def test_pushing_a_slipped_deadline_back_clears_it(goals_client: TestClient) -> None:
    start = (today() - timedelta(days=30)).isoformat()
    goal = create_goal(
        goals_client, no_sugar(startDate=start, deadline=(today() - timedelta(days=1)).isoformat())
    )

    pushed = update_goal(
        goals_client, goal["id"], edit(deadline=(today() + timedelta(days=7)).isoformat())
    ).json()

    assert (goal["slipped"], pushed["slipped"]) == (True, False)


def test_a_deadline_before_the_start_date_is_not_allowed(goals_client: TestClient) -> None:
    goal = create_goal(goals_client, no_sugar(startDate="2026-11-01"))

    response = update_goal(goals_client, goal["id"], edit(deadline="2026-10-31"))

    assert response.status_code == 409


def test_a_goal_can_move_between_active_aspirations_or_to_none(goals_client: TestClient) -> None:
    first = create_aspiration(goals_client, "First")
    second = create_aspiration(goals_client, "Second")
    goal = create_goal(goals_client, lifting(aspirationId=first["id"]))

    moved = update_goal(goals_client, goal["id"], edit(aspirationId=second["id"])).json()
    loose = update_goal(goals_client, goal["id"], edit()).json()

    assert (moved["aspirationId"], loose["aspirationId"]) == (second["id"], None)


def test_moving_to_a_retired_aspiration_is_not_allowed(goals_client: TestClient) -> None:
    retired = create_aspiration(goals_client, "Sail")
    goals_client.post(f"/api/aspirations/{retired['id']}/retire", json={"itsWork": "keep"})
    goal = create_goal(goals_client, lifting())

    response = update_goal(goals_client, goal["id"], edit(aspirationId=retired["id"]))

    assert response.status_code == 409


def test_a_goal_can_stay_under_its_retired_aspiration(goals_client: TestClient) -> None:
    aspiration = create_aspiration(goals_client, "Sail")
    goal = create_goal(goals_client, lifting(aspirationId=aspiration["id"]))
    goals_client.post(f"/api/aspirations/{aspiration['id']}/retire", json={"itsWork": "keep"})

    response = update_goal(goals_client, goal["id"], edit(aspirationId=aspiration["id"]))

    assert response.status_code == 200, response.text


def test_update_of_another_users_goal_or_aspiration_is_not_found(
    goals_client: TestClient, connection: Connection
) -> None:
    other_user = add_other_user(connection)
    their_goal = add_goal_for(connection, other_user)
    their_aspiration = add_aspiration_for(connection, other_user, "Theirs")
    mine = create_goal(goals_client, lifting())

    assert update_goal(goals_client, str(their_goal), edit()).status_code == 404
    assert update_goal(goals_client, str(uuid4()), edit()).status_code == 404
    response = update_goal(goals_client, mine["id"], edit(aspirationId=str(their_aspiration)))
    assert response.status_code == 404


@pytest.mark.parametrize("changes", [{"label": ""}, {"measurableLine": " "}, {"label": None}])
def test_an_edit_that_breaks_the_rules_is_refused(
    goals_client: TestClient, changes: dict[str, Any]
) -> None:
    goal = create_goal(goals_client, lifting())

    assert update_goal(goals_client, goal["id"], edit(**changes)).status_code == 422


def test_update_is_audited(goals_client: TestClient, connection: Connection) -> None:
    goal = create_goal(goals_client, lifting())

    update_goal(goals_client, goal["id"], edit())

    assert [row.action for row in audit_rows(connection, goal["id"])] == [
        "create goal",
        "update goal",
    ]


# setWeeklyTarget


def set_target(client: TestClient, goal_id: str, body: dict[str, Any]) -> Any:
    return client.put(f"/api/goals/{goal_id}/weekly-target", json=body)


FOUR_RUNS = {"kind": "amount", "sessions": 4, "amount": 25, "unit": "miles"}


def target_rows(connection: Connection, goal_id: str) -> list[tuple[date, int]]:
    rows = connection.execute(
        text(
            "select effective_from, sessions from weekly_targets where goal_id = :goal_id"
            " order by effective_from"
        ),
        {"goal_id": goal_id},
    )
    return [(row.effective_from, row.sessions) for row in rows]


def test_a_change_this_week_replaces_this_weeks_target(
    goals_client: TestClient, connection: Connection
) -> None:
    goal = create_goal(goals_client, lifting())

    response = set_target(goals_client, goal["id"], FOUR_RUNS)

    assert response.status_code == 200, response.text
    assert response.json()["weeklyTarget"] == {
        "kind": "amount",
        "sessions": 4,
        "amount": 25,
        "unit": "miles",
        "effectiveFrom": week_of(today()).isoformat(),
    }
    assert target_rows(connection, goal["id"]) == [(week_of(today()), 4)]


def test_once_next_week_is_open_a_change_starts_next_week(
    goals_client: TestClient, connection: Connection
) -> None:
    goal = create_goal(goals_client, lifting())
    next_week = week_of(today()) + timedelta(weeks=1)
    connection.execute(
        text("update users set planned_through_week = :week where id = :id"),
        {"week": next_week, "id": FIXED_USER_ID},
    )

    changed = set_target(goals_client, goal["id"], FOUR_RUNS).json()

    assert changed["weeklyTarget"]["effectiveFrom"] == next_week.isoformat()
    assert target_rows(connection, goal["id"]) == [(week_of(today()), 3), (next_week, 4)]


def test_last_weeks_target_is_kept(goals_client: TestClient, connection: Connection) -> None:
    goal = create_goal(goals_client, lifting())
    last_week = week_of(today()) - timedelta(weeks=1)
    connection.execute(
        text("update weekly_targets set effective_from = :week where goal_id = :goal_id"),
        {"week": last_week, "goal_id": goal["id"]},
    )

    set_target(goals_client, goal["id"], FOUR_RUNS)

    assert target_rows(connection, goal["id"]) == [(last_week, 3), (week_of(today()), 4)]


def test_the_same_target_again_changes_nothing(
    goals_client: TestClient, connection: Connection
) -> None:
    goal = create_goal(goals_client, lifting())
    first = set_target(goals_client, goal["id"], FOUR_RUNS).json()

    again = set_target(goals_client, goal["id"], FOUR_RUNS).json()

    assert again == first
    actions = connection.execute(
        text(
            "select action from audit_log where row_id in"
            " (select id from weekly_targets where goal_id = :goal_id) order by id"
        ),
        {"goal_id": goal["id"]},
    ).scalars()
    assert list(actions) == ["create goal", "set weekly target"]


@pytest.mark.parametrize("goal_type", ["quitting", "oneOff"])
def test_only_a_building_goal_has_a_target(goals_client: TestClient, goal_type: str) -> None:
    goal = create_goal(goals_client, no_sugar(type=goal_type))

    assert set_target(goals_client, goal["id"], FOUR_RUNS).status_code == 409


def test_a_target_for_another_users_goal_is_not_found(
    goals_client: TestClient, connection: Connection
) -> None:
    theirs = add_goal_for(connection, add_other_user(connection))

    assert set_target(goals_client, str(theirs), FOUR_RUNS).status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "amount", "sessions": 4, "unit": "miles"},
        {"kind": "count", "sessions": 4, "amount": 5, "unit": "runs"},
        {"kind": "count", "sessions": 15, "unit": "runs"},
        {"kind": "count", "sessions": 3, "unit": ""},
    ],
)
def test_a_target_that_breaks_the_rules_is_refused(
    goals_client: TestClient, body: dict[str, Any]
) -> None:
    goal = create_goal(goals_client, lifting())

    assert set_target(goals_client, goal["id"], body).status_code == 422
