from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.config import FIXED_USER_ID
from app.weeks import week_of
from tests.test_aspirations import add_aspiration_for, add_other_user, audit_rows
from tests.test_aspirations import create as create_aspiration
from tests.test_goal_tasks import week_titles
from tests.test_goals import add_goal_for, create_goal, lifting, today
from tests.test_tasks import open_next_week, rows

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


def test_an_item_can_be_edited_while_it_stays_under_its_retired_aspiration(
    items_client: TestClient,
) -> None:
    aspiration = create_aspiration(items_client, "Keep a home")
    created = create(items_client, item(aspirationId=aspiration["id"]))
    items_client.post(f"/api/aspirations/{aspiration['id']}/retire", json={"itsWork": "pause"})

    edited = edit(items_client, created["id"], item(name="Trash", aspirationId=aspiration["id"]))

    assert edited["name"] == "Trash"
    assert edited["aspirationId"] == aspiration["id"]


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


# turnOffRecurringItem, turnOnRecurringItem


def recurring_task(
    connection: Connection,
    item_id: str,
    week: date,
    day: date | None = None,
    by_hand: bool = False,
    state: str = "open",
) -> str:
    """A task made from the item, as week-turnover will make them, with its row in the week."""
    task_id = str(uuid4())
    done = state == "done"
    connection.execute(
        text(
            "insert into tasks (id, user_id, title, origin, recurring_item_id, period_start,"
            " number, state, completed_at, completed_on) values (:id, :user_id, 'Trash',"
            " 'recurring_item', :item, :week,"
            " (select count(*) + 1 from tasks where recurring_item_id = :item),"
            " :state, :at, :on)"
        ),
        {
            "id": task_id,
            "user_id": FIXED_USER_ID,
            "item": item_id,
            "week": week,
            "state": state,
            "at": datetime.now(UTC) if done else None,
            "on": day if done else None,
        },
    )
    connection.execute(
        text(
            "insert into task_weeks (id, user_id, task_id, week, planned_day, placed_by_hand,"
            " outcome) values (:id, :user_id, :task, :week, :day, :by_hand, :outcome)"
        ),
        {
            "id": uuid4(),
            "user_id": FIXED_USER_ID,
            "task": task_id,
            "week": week,
            "day": day,
            "by_hand": by_hand,
            "outcome": "done" if done else None,
        },
    )
    return task_id


def turn(client: TestClient, item_id: str, way: str) -> Any:
    response = client.post(f"/api/recurring-items/{item_id}/turn-{way}")
    assert response.status_code == 200, response.text
    return response.json()


def test_turning_off_sets_open_tasks_aside_keeping_their_day(
    items_client: TestClient, connection: Connection
) -> None:
    created = create(items_client, item())
    this_week = week_of(today())
    bank = recurring_task(connection, created["id"], this_week)
    placed = recurring_task(connection, created["id"], this_week, today(), by_hand=True)
    done = recurring_task(connection, created["id"], this_week, today(), state="done")

    turned = turn(items_client, created["id"], "off")

    assert turned == created | {"active": False}
    assert rows(connection, bank) == [(this_week, None, False, "set_aside")]
    assert rows(connection, placed) == [(this_week, today(), True, "set_aside")]
    assert rows(connection, done) == [(this_week, today(), False, "done")]
    assert week_titles(items_client, this_week) == ["Trash"]


def test_turning_on_returns_tasks_to_their_weeks_bank_but_not_a_closed_weeks(
    items_client: TestClient, connection: Connection
) -> None:
    open_next_week(connection)
    created = create(items_client, item())
    this_week = week_of(today())
    next_week = this_week + timedelta(weeks=1)
    last_week = this_week - timedelta(weeks=1)
    placed = recurring_task(connection, created["id"], this_week, today(), by_hand=True)
    later = recurring_task(connection, created["id"], next_week)
    turn(items_client, created["id"], "off")
    old = recurring_task(connection, created["id"], last_week)
    connection.execute(
        text("update task_weeks set outcome = 'set_aside' where task_id = :id"), {"id": old}
    )

    turned = turn(items_client, created["id"], "on")

    assert turned["active"] is True
    assert rows(connection, placed) == [(this_week, None, False, None)]
    assert rows(connection, later) == [(next_week, None, False, None)]
    assert rows(connection, old) == [(last_week, None, False, "set_aside")]


def test_turning_off_and_on_sent_twice_changes_nothing_more(
    items_client: TestClient, connection: Connection
) -> None:
    created = create(items_client, item())
    task = recurring_task(connection, created["id"], week_of(today()), today(), by_hand=True)

    turn(items_client, created["id"], "off")
    assert turn(items_client, created["id"], "off")["active"] is False
    turn(items_client, created["id"], "on")
    assert turn(items_client, created["id"], "on")["active"] is True

    assert rows(connection, task) == [(week_of(today()), None, False, None)]
    assert [row.action for row in audit_rows(connection, created["id"])] == [
        "create recurring item",
        "turn off recurring item",
        "turn on recurring item",
    ]


def test_turning_on_under_a_retired_aspiration_makes_it_maintenance(
    items_client: TestClient,
) -> None:
    aspiration = create_aspiration(items_client, "Keep a home")
    created = create(items_client, item(aspirationId=aspiration["id"]))
    turn(items_client, created["id"], "off")
    items_client.post(f"/api/aspirations/{aspiration['id']}/retire", json={"itsWork": "pause"})

    turned = turn(items_client, created["id"], "on")

    assert turned["aspirationId"] is None


@pytest.mark.parametrize("way", ["off", "on"])
@pytest.mark.parametrize("owner", ["nobody", "someone else"])
def test_turning_an_unknown_or_another_owners_item_is_not_found(
    items_client: TestClient, connection: Connection, owner: str, way: str
) -> None:
    item_id = uuid4() if owner == "nobody" else add_item_for(connection, add_other_user(connection))

    response = items_client.post(f"/api/recurring-items/{item_id}/turn-{way}")

    assert response.status_code == 404, response.text


# Retiring an aspiration


def retire(client: TestClient, aspiration_id: str, its_work: str) -> None:
    response = client.post(f"/api/aspirations/{aspiration_id}/retire", json={"itsWork": its_work})
    assert response.status_code == 200, response.text


def test_retiring_with_its_work_paused_turns_its_items_off(
    items_client: TestClient, connection: Connection
) -> None:
    home = create_aspiration(items_client, "Keep a home")
    fit = create_aspiration(items_client, "Be fit")
    rent = create(items_client, item(**RENT, aspirationId=home["id"]))
    stretch = create(items_client, item(name="Stretch", aspirationId=fit["id"]))
    trash = create(items_client, item())
    this_week = week_of(today())
    task = recurring_task(connection, rent["id"], this_week, today(), by_hand=True)

    retire(items_client, home["id"], "pause")

    assert {row["name"]: (row["active"], row["aspirationId"]) for row in listed(items_client)} == {
        rent["name"]: (False, home["id"]),
        stretch["name"]: (True, fit["id"]),
        trash["name"]: (True, None),
    }
    assert rows(connection, task) == [(this_week, today(), True, "set_aside")]


def test_retiring_keeping_its_work_makes_its_items_maintenance(
    items_client: TestClient, connection: Connection
) -> None:
    home = create_aspiration(items_client, "Keep a home")
    rent = create(items_client, item(**RENT, aspirationId=home["id"]))
    off = create(items_client, item(aspirationId=home["id"]))
    turn(items_client, off["id"], "off")
    task = recurring_task(connection, rent["id"], week_of(today()), today(), by_hand=True)

    retire(items_client, home["id"], "keep")

    assert {row["name"]: (row["active"], row["aspirationId"]) for row in listed(items_client)} == {
        rent["name"]: (True, None),
        off["name"]: (False, None),
    }
    assert rows(connection, task) == [(week_of(today()), today(), True, None)]


def test_bringing_an_aspiration_back_leaves_its_items_off(items_client: TestClient) -> None:
    home = create_aspiration(items_client, "Keep a home")
    rent = create(items_client, item(**RENT, aspirationId=home["id"]))
    retire(items_client, home["id"], "pause")

    items_client.post(f"/api/aspirations/{home['id']}/bring-back")

    assert listed(items_client) == [rent | {"active": False}]


def test_retiring_again_changes_no_item(items_client: TestClient) -> None:
    home = create_aspiration(items_client, "Keep a home")
    rent = create(items_client, item(**RENT, aspirationId=home["id"]))
    retire(items_client, home["id"], "pause")

    retire(items_client, home["id"], "keep")

    assert listed(items_client) == [rent | {"active": False}]


def test_an_uncheck_while_the_item_is_off_stays_set_aside(
    items_client: TestClient, connection: Connection
) -> None:
    created = create(items_client, item())
    this_week = week_of(today())
    task = recurring_task(connection, created["id"], this_week, today(), state="done")
    turn(items_client, created["id"], "off")

    response = items_client.post(f"/api/tasks/{task}/uncheck")

    assert response.status_code == 200, response.text
    assert rows(connection, task) == [(this_week, today(), False, "set_aside")]
