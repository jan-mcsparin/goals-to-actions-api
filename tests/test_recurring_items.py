from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.config import FIXED_USER_ID
from tests.test_aspirations import add_aspiration_for, add_other_user, audit_rows
from tests.test_aspirations import create as create_aspiration
from tests.test_goals import add_goal_for, create_goal, lifting

ZONE = "America/Denver"

TRASH = {"name": "Take out the trash", "schedule": {"kind": "weekly", "weekday": "tuesday"}}
RENT = {"name": "Pay rent", "schedule": {"kind": "monthly", "dayOfMonth": 1}}
LAUNDRY = {"name": "Laundry", "schedule": {"kind": "flexible", "times": 1, "period": "week"}}
BATHROOM = {
    "name": "Clean the bathroom",
    "schedule": {"kind": "flexible", "times": 1, "period": "twoWeeks"},
}


@pytest.fixture
def items_client(client: TestClient) -> Iterator[TestClient]:
    """Retiring and turning on and off need the day, so every request sends the time zone."""
    client.headers["X-Time-Zone"] = ZONE
    yield client


def item(**changes: Any) -> dict[str, Any]:
    return TRASH | {"startsOn": "2026-11-17"} | changes


def create(client: TestClient, body: dict[str, Any], item_id: UUID | None = None) -> Any:
    response = client.put(f"/api/recurring-items/{item_id or uuid4()}", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def listed(client: TestClient) -> list[dict[str, Any]]:
    response = client.get("/api/recurring-items")
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["recurringItems"]
    return items


def add_item_for(connection: Connection, user_id: UUID) -> UUID:
    item_id = uuid4()
    connection.execute(
        text(
            "insert into recurring_items (id, user_id, name, schedule_kind, weekday, starts_on)"
            " values (:id, :user_id, 'Theirs', 'weekly', 1, '2026-11-16')"
        ),
        {"id": item_id, "user_id": user_id},
    )
    return item_id


# createRecurringItem


def test_create_returns_the_item_turned_on(items_client: TestClient) -> None:
    item_id = uuid4()

    created = create(items_client, item(), item_id)

    assert created == {
        "id": str(item_id),
        "name": "Take out the trash",
        "aspirationId": None,
        "fromGoalId": None,
        "schedule": {"kind": "weekly", "weekday": "tuesday"},
        "startsOn": "2026-11-17",
        "active": True,
        "createdAt": created["createdAt"],
    }


@pytest.mark.parametrize(
    "schedule",
    [
        {"kind": "weekly", "weekday": "sunday"},
        {"kind": "weekly", "weekday": "monday"},
        {"kind": "monthly", "dayOfMonth": 28},
        {"kind": "flexible", "times": 6, "period": "week"},
        {"kind": "flexible", "times": 1, "period": "twoWeeks"},
        {"kind": "flexible", "times": 1, "period": "month"},
    ],
)
def test_each_schedule_comes_back_as_sent(
    items_client: TestClient, schedule: dict[str, Any]
) -> None:
    assert create(items_client, item(schedule=schedule))["schedule"] == schedule


@pytest.mark.parametrize(
    "schedule",
    [
        {"kind": "weekly"},
        {"kind": "weekly", "weekday": "tues"},
        {"kind": "monthly", "dayOfMonth": 29},
        {"kind": "monthly", "dayOfMonth": 0},
        {"kind": "flexible", "times": 7, "period": "week"},
        {"kind": "flexible", "times": 2, "period": "twoWeeks"},
        {"kind": "flexible", "times": 2, "period": "month"},
        {"kind": "flexible", "times": 1, "period": "year"},
        {"kind": "yearly"},
    ],
)
def test_a_schedule_that_does_not_fit_is_refused(
    items_client: TestClient, schedule: dict[str, Any]
) -> None:
    response = items_client.put(f"/api/recurring-items/{uuid4()}", json=item(schedule=schedule))

    assert response.status_code == 422, response.text


@pytest.mark.parametrize("name", ["", "   ", "x" * 201, "Trash\x00"])
def test_a_bad_name_is_refused(items_client: TestClient, name: str) -> None:
    response = items_client.put(f"/api/recurring-items/{uuid4()}", json=item(name=name))

    assert response.status_code == 422, response.text


def test_create_sent_twice_makes_one_item(items_client: TestClient) -> None:
    item_id = uuid4()
    first = create(items_client, item(), item_id)

    again = create(items_client, item(name="Something else"), item_id)

    assert again == first
    assert len(listed(items_client)) == 1


def test_an_item_can_go_under_an_aspiration(items_client: TestClient) -> None:
    aspiration = create_aspiration(items_client, "Be fit")

    created = create(items_client, item(aspirationId=aspiration["id"]))

    assert created["aspirationId"] == aspiration["id"]


def test_an_item_cannot_go_under_a_retired_aspiration(items_client: TestClient) -> None:
    aspiration = create_aspiration(items_client, "Be fit")
    items_client.post(f"/api/aspirations/{aspiration['id']}/retire", json={"itsWork": "keep"})

    response = items_client.put(
        f"/api/recurring-items/{uuid4()}", json=item(aspirationId=aspiration["id"])
    )

    assert response.status_code == 409, response.text


def test_an_item_cannot_go_under_another_owners_aspiration(
    items_client: TestClient, connection: Connection
) -> None:
    theirs = add_aspiration_for(connection, add_other_user(connection), "Theirs")

    response = items_client.put(
        f"/api/recurring-items/{uuid4()}", json=item(aspirationId=str(theirs))
    )

    assert response.status_code == 404, response.text


def test_a_reached_goals_practice_can_be_kept(items_client: TestClient) -> None:
    aspiration = create_aspiration(items_client, "Be fit")
    goal = create_goal(items_client, lifting(aspirationId=aspiration["id"]))
    items_client.post(f"/api/goals/{goal['id']}/mark-reached")

    kept = create(
        items_client,
        item(
            name="Lifting",
            schedule={"kind": "flexible", "times": 3, "period": "week"},
            aspirationId=aspiration["id"],
            fromGoalId=goal["id"],
        ),
    )

    assert kept["fromGoalId"] == goal["id"]


def test_an_item_cannot_keep_another_owners_goal(
    items_client: TestClient, connection: Connection
) -> None:
    theirs = add_goal_for(connection, add_other_user(connection))

    response = items_client.put(
        f"/api/recurring-items/{uuid4()}", json=item(fromGoalId=str(theirs))
    )

    assert response.status_code == 404, response.text


def test_create_is_in_the_audit_log(items_client: TestClient, connection: Connection) -> None:
    created = create(items_client, item())

    assert audit_rows(connection, created["id"]) == [(FIXED_USER_ID, "create recurring item")]


# listRecurringItems


def test_the_list_has_every_item_oldest_first(
    items_client: TestClient, connection: Connection
) -> None:
    aspiration = create_aspiration(items_client, "Keep a home")
    trash = create(items_client, item())
    rent = create(items_client, item(**RENT, aspirationId=aspiration["id"]))
    laundry = create(items_client, item(**LAUNDRY))
    # One test is one transaction, so every row has the same created_at until it's spread out.
    for minutes, row in enumerate([trash, rent, laundry]):
        connection.execute(
            text(
                "update recurring_items set created_at = now() + make_interval(mins => :m)"
                " where id = :id"
            ),
            {"m": minutes, "id": row["id"]},
        )

    assert [row["id"] for row in listed(items_client)] == [trash["id"], rent["id"], laundry["id"]]


def test_the_list_leaves_out_deleted_items_and_other_owners(
    items_client: TestClient, connection: Connection
) -> None:
    add_item_for(connection, add_other_user(connection))
    gone = create(items_client, item(**BATHROOM))
    connection.execute(
        text("update recurring_items set deleted_at = now() where id = :id"), {"id": gone["id"]}
    )

    assert listed(items_client) == []


# updateRecurringItem


def edit(client: TestClient, item_id: str, body: dict[str, Any]) -> Any:
    response = client.patch(f"/api/recurring-items/{item_id}", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_an_edit_changes_name_schedule_and_start(items_client: TestClient) -> None:
    created = create(items_client, item())

    edited = edit(items_client, created["id"], item(**RENT, startsOn="2026-12-01"))

    assert edited == created | {
        "name": "Pay rent",
        "schedule": {"kind": "monthly", "dayOfMonth": 1},
        "startsOn": "2026-12-01",
    }
    assert listed(items_client) == [edited]


def test_an_edit_can_move_an_item_to_and_from_an_aspiration(items_client: TestClient) -> None:
    aspiration = create_aspiration(items_client, "Keep a home")
    created = create(items_client, item())

    moved = edit(items_client, created["id"], item(aspirationId=aspiration["id"]))
    back = edit(items_client, created["id"], item())

    assert moved["aspirationId"] == aspiration["id"]
    assert back["aspirationId"] is None


def test_an_edit_keeps_the_goal_it_came_from(items_client: TestClient) -> None:
    goal = create_goal(items_client, lifting())
    created = create(items_client, item(fromGoalId=goal["id"]))

    edited = edit(items_client, created["id"], item(name="Lifting"))

    assert edited["fromGoalId"] == goal["id"]


def test_an_item_cannot_be_moved_under_a_retired_aspiration(items_client: TestClient) -> None:
    aspiration = create_aspiration(items_client, "Be fit")
    items_client.post(f"/api/aspirations/{aspiration['id']}/retire", json={"itsWork": "keep"})
    created = create(items_client, item())

    response = items_client.patch(
        f"/api/recurring-items/{created['id']}", json=item(aspirationId=aspiration["id"])
    )

    assert response.status_code == 409, response.text


@pytest.mark.parametrize("owner", ["nobody", "someone else"])
def test_an_edit_to_an_unknown_or_another_owners_item_is_not_found(
    items_client: TestClient, connection: Connection, owner: str
) -> None:
    item_id = uuid4() if owner == "nobody" else add_item_for(connection, add_other_user(connection))

    response = items_client.patch(f"/api/recurring-items/{item_id}", json=item())

    assert response.status_code == 404, response.text


def test_an_edit_sent_twice_changes_nothing_more(items_client: TestClient) -> None:
    created = create(items_client, item())
    first = edit(items_client, created["id"], item(**LAUNDRY))

    assert edit(items_client, created["id"], item(**LAUNDRY)) == first


def test_an_edit_is_in_the_audit_log(items_client: TestClient, connection: Connection) -> None:
    created = create(items_client, item())

    edit(items_client, created["id"], item(name="Trash and recycling"))

    assert [row.action for row in audit_rows(connection, created["id"])] == [
        "create recurring item",
        "update recurring item",
    ]
