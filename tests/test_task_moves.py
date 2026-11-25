"""The plan edits: place on a day, back to the bank, swap and drop. Each names the week it
was made in, and is refused once the task has left it."""

from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.weeks import week_of
from tests.test_aspirations import add_other_user
from tests.test_check_off import check_off
from tests.test_goals import ZONE, create_goal, lifting, today
from tests.test_tasks import add_task, add_task_for, open_next_week, row_actions, rows


@pytest.fixture
def tasks_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


def this_week() -> date:
    return week_of(today())


def next_week() -> date:
    return this_week() + timedelta(weeks=1)


def last_day_this_week() -> date:
    return this_week() + timedelta(days=6)


def place(client: TestClient, task_id: str, day: date, week: date | None = None) -> Any:
    week = week or week_of(day)
    return client.post(
        f"/api/tasks/{task_id}/place", json={"week": week.isoformat(), "day": day.isoformat()}
    )


def to_bank(client: TestClient, task_id: str, week: date | None = None) -> Any:
    return client.post(
        f"/api/tasks/{task_id}/bank", json={"week": (week or this_week()).isoformat()}
    )


def move_to_last_week(connection: Connection, task_id: str) -> None:
    connection.execute(
        text("update task_weeks set week = :week, planned_day = null where task_id = :id"),
        {"week": this_week() - timedelta(weeks=1), "id": task_id},
    )


# placeTask


def test_placing_puts_a_bank_task_on_a_day_placed_by_hand(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client)

    response = place(tasks_client, task["id"], today())

    assert response.status_code == 200, response.text
    assert response.json() == task | {"plannedDay": today().isoformat(), "placedByHand": True}
    assert row_actions(connection, task["id"]) == ["add task", "place task"]


def test_placing_moves_a_task_to_another_day(tasks_client: TestClient) -> None:
    task = add_task(tasks_client, day=today().isoformat())

    moved = place(tasks_client, task["id"], last_day_this_week()).json()

    assert moved["plannedDay"] == last_day_this_week().isoformat()


def test_the_same_placing_twice_changes_nothing_more(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client)
    first = place(tasks_client, task["id"], today()).json()

    assert place(tasks_client, task["id"], today()).json() == first
    assert rows(connection, task["id"]) == [(this_week(), today(), True, None)]


def test_next_weeks_tasks_can_be_placed_on_its_days(
    tasks_client: TestClient, connection: Connection
) -> None:
    open_next_week(connection)
    task = add_task(tasks_client, dueDate=next_week().isoformat())

    response = place(tasks_client, task["id"], next_week() + timedelta(days=2))

    assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    "day",
    [
        lambda: today() - timedelta(days=1),
        lambda: this_week() - timedelta(days=1),
    ],
    ids=["a past day", "a day in an earlier week"],
)
def test_placing_on_a_day_not_allowed_is_refused(tasks_client: TestClient, day: Any) -> None:
    task = add_task(tasks_client)

    assert place(tasks_client, task["id"], day(), week=this_week()).status_code == 409


# Across weeks (spec `on-a-day`)

DECEMBER_DAY = date(2026, 12, 9)


def test_a_task_moves_to_a_day_in_a_later_week_and_back(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client, day=today().isoformat())

    away = place(tasks_client, task["id"], DECEMBER_DAY, week=this_week())
    assert away.status_code == 200, away.text
    assert (away.json()["week"], away.json()["plannedDay"]) == ("2026-12-07", "2026-12-09")
    assert rows(connection, task["id"]) == [(date(2026, 12, 7), DECEMBER_DAY, True, None)]

    tomorrow = today() + timedelta(days=1)
    back = place(tasks_client, task["id"], tomorrow, week=date(2026, 12, 7))
    assert back.status_code == 200, back.text
    assert rows(connection, task["id"]) == [(this_week(), tomorrow, True, None)]
    assert task["id"] in [row["id"] for row in week_read(tasks_client)["tasks"]]


def test_a_pinned_task_moves_from_one_later_week_to_another(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client, day=DECEMBER_DAY.isoformat())
    later = date(2027, 1, 14)

    response = place(tasks_client, task["id"], later, week=date(2026, 12, 7))

    assert response.status_code == 200, response.text
    assert rows(connection, task["id"]) == [(week_of(later), later, True, None)]
    assert row_actions(connection, task["id"]) == ["add task", "place task"]


def test_a_bank_task_moves_to_a_later_week(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client)

    assert place(tasks_client, task["id"], DECEMBER_DAY, week=this_week()).status_code == 200
    assert rows(connection, task["id"]) == [(date(2026, 12, 7), DECEMBER_DAY, True, None)]


def test_a_goal_session_stays_in_its_week(tasks_client: TestClient) -> None:
    create_goal(tasks_client, lifting())
    session = next(row for row in week_read(tasks_client)["tasks"] if row["goalId"])

    response = place(tasks_client, session["id"], next_week() + timedelta(days=1), this_week())

    assert response.status_code == 409
    assert place(tasks_client, session["id"], last_day_this_week()).status_code == 200


def test_a_move_onto_a_week_the_task_already_has_a_row_in_is_refused(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client, day=today().isoformat())
    connection.execute(
        text(
            "insert into task_weeks (id, user_id, task_id, week, outcome)"
            " select gen_random_uuid(), user_id, task_id, :week, 'rolled_over' from task_weeks"
            " where task_id = :id"
        ),
        {"week": date(2026, 12, 7), "id": task["id"]},
    )

    assert place(tasks_client, task["id"], DECEMBER_DAY, week=this_week()).status_code == 409


def test_a_queued_move_after_the_task_left_its_week_is_refused(tasks_client: TestClient) -> None:
    task = add_task(tasks_client, day=today().isoformat())
    place(tasks_client, task["id"], DECEMBER_DAY, week=this_week())

    stale = place(tasks_client, task["id"], last_day_this_week(), week=this_week())

    assert stale.status_code == 409
    assert stale.json()["detail"] == "The task has moved on to another week."


def test_a_pinned_task_can_be_dropped(tasks_client: TestClient, connection: Connection) -> None:
    task = add_task(tasks_client, day=DECEMBER_DAY.isoformat())

    dropped = tasks_client.post(f"/api/tasks/{task['id']}/drop")

    assert dropped.status_code == 200, dropped.text
    assert dropped.json()["state"] == "dropped"
    assert rows(connection, task["id"]) == [(date(2026, 12, 7), DECEMBER_DAY, True, "dropped")]


def week_read(client: TestClient) -> Any:
    return client.get(f"/api/weeks/{this_week()}").json()


def test_a_placing_made_in_a_week_the_task_has_left_is_refused(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client)
    move_to_last_week(connection, task["id"])

    assert place(tasks_client, task["id"], today(), week=this_week()).status_code == 409
    assert to_bank(tasks_client, task["id"]).status_code == 409


def test_a_task_not_in_play_cannot_be_placed(tasks_client: TestClient) -> None:
    waiting = add_task(tasks_client, dueDate=(today() + timedelta(days=8)).isoformat())
    done = add_task(tasks_client)
    check_off(tasks_client, done["id"])

    assert place(tasks_client, waiting["id"], today()).status_code == 409
    assert place(tasks_client, done["id"], today()).status_code == 409


def test_another_users_task_is_not_found(tasks_client: TestClient, connection: Connection) -> None:
    theirs = str(add_task_for(connection, add_other_user(connection)))

    assert place(tasks_client, theirs, today()).status_code == 404
    assert to_bank(tasks_client, theirs).status_code == 404
    assert to_bank(tasks_client, str(uuid4())).status_code == 404


# moveTaskToBank


def test_back_to_the_bank_clears_the_day_and_the_mark(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client, day=today().isoformat())

    response = to_bank(tasks_client, task["id"])

    assert response.status_code == 200, response.text
    assert response.json() == task | {"plannedDay": None, "placedByHand": False}
    assert to_bank(tasks_client, task["id"]).json() == response.json()
    assert rows(connection, task["id"]) == [(this_week(), None, False, None)]
    assert row_actions(connection, task["id"])[-1] == "move task to bank"


# swapTasks


def swap(
    client: TestClient, task_id: str, bank_task_id: str, day: date, week: date | None = None
) -> Any:
    return client.post(
        f"/api/tasks/{task_id}/swap",
        json={
            "week": (week or this_week()).isoformat(),
            "bankTaskId": bank_task_id,
            "day": day.isoformat(),
        },
    )


def test_a_swap_sends_the_days_task_to_the_bank_and_places_the_bank_task(
    tasks_client: TestClient, connection: Connection
) -> None:
    on_today = add_task(tasks_client, title="On today", day=today().isoformat())
    in_bank = add_task(tasks_client, title="In the bank")

    response = swap(tasks_client, on_today["id"], in_bank["id"], today())

    assert response.status_code == 200, response.text
    assert response.json() == {
        "toBank": on_today | {"plannedDay": None, "placedByHand": False},
        "placed": in_bank | {"plannedDay": today().isoformat(), "placedByHand": True},
    }
    assert row_actions(connection, in_bank["id"])[-1] == "swap tasks"


def test_the_same_swap_twice_changes_nothing_more(tasks_client: TestClient) -> None:
    on_today = add_task(tasks_client, day=today().isoformat())
    in_bank = add_task(tasks_client)
    first = swap(tasks_client, on_today["id"], in_bank["id"], today()).json()

    assert swap(tasks_client, on_today["id"], in_bank["id"], today()).json() == first


def test_a_swap_is_refused_whole_when_either_task_has_left_the_week(
    tasks_client: TestClient, connection: Connection
) -> None:
    on_today = add_task(tasks_client, day=today().isoformat())
    in_bank = add_task(tasks_client)
    move_to_last_week(connection, in_bank["id"])

    assert swap(tasks_client, on_today["id"], in_bank["id"], today()).status_code == 409
    assert rows(connection, on_today["id"]) == [(this_week(), today(), True, None)]


def test_a_swap_onto_a_past_day_or_with_itself_is_refused(tasks_client: TestClient) -> None:
    on_today = add_task(tasks_client, day=today().isoformat())
    in_bank = add_task(tasks_client)
    yesterday = today() - timedelta(days=1)

    assert swap(tasks_client, on_today["id"], in_bank["id"], yesterday).status_code == 409
    assert swap(tasks_client, on_today["id"], on_today["id"], today()).status_code == 409


def test_a_swap_with_another_users_task_is_not_found(
    tasks_client: TestClient, connection: Connection
) -> None:
    on_today = add_task(tasks_client, day=today().isoformat())
    theirs = str(add_task_for(connection, add_other_user(connection)))

    assert swap(tasks_client, on_today["id"], theirs, today()).status_code == 404
    assert swap(tasks_client, theirs, on_today["id"], today()).status_code == 404


# dropTask


def drop(client: TestClient, task_id: str) -> Any:
    return client.post(f"/api/tasks/{task_id}/drop")


def test_a_dropped_task_closes_its_row_and_leaves_the_week(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client, day=today().isoformat())

    response = drop(tasks_client, task["id"])

    assert response.status_code == 200, response.text
    assert response.json() == task | {
        "state": "dropped",
        "week": None,
        "plannedDay": None,
        "placedByHand": False,
        "atClose": None,
    }
    assert rows(connection, task["id"]) == [(this_week(), today(), True, "dropped")]
    week = tasks_client.get(f"/api/weeks/{this_week().isoformat()}").json()
    assert week["tasks"] == []
    assert drop(tasks_client, task["id"]).json() == response.json()


def test_a_waiting_task_can_be_dropped(tasks_client: TestClient, connection: Connection) -> None:
    waiting = add_task(tasks_client, dueDate=(today() + timedelta(days=8)).isoformat())

    assert drop(tasks_client, waiting["id"]).json()["state"] == "dropped"
    assert rows(connection, waiting["id"]) == []


def test_a_done_task_cannot_be_dropped(tasks_client: TestClient, connection: Connection) -> None:
    task = add_task(tasks_client)
    check_off(tasks_client, task["id"])

    assert drop(tasks_client, task["id"]).status_code == 409
    theirs = str(add_task_for(connection, add_other_user(connection)))
    assert drop(tasks_client, theirs).status_code == 404
