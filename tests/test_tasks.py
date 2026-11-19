from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.config import FIXED_USER_ID
from app.tasks.models import NewTask
from app.tasks.rules import Landing, landing
from app.weeks import OpenWeeks, week_of
from tests.test_aspirations import add_other_user, audit_rows
from tests.test_goals import ZONE, add_goal_for, create_goal, lifting, today


@pytest.fixture
def tasks_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


def add_task(client: TestClient, task_id: UUID | None = None, **body: Any) -> Any:
    response = client.put(
        f"/api/tasks/{task_id or uuid4()}", json={"title": "Call the dentist"} | body
    )
    assert response.status_code == 200, response.text
    return response.json()


def add_task_for(connection: Connection, user_id: UUID) -> UUID:
    task_id = uuid4()
    connection.execute(
        text(
            "insert into tasks (id, user_id, title, origin)"
            " values (:id, :user_id, 'Theirs', 'by_hand')"
        ),
        {"id": task_id, "user_id": user_id},
    )
    return task_id


def rows(connection: Connection, task_id: str) -> list[Any]:
    return list(
        connection.execute(
            text(
                "select week, planned_day, placed_by_hand, outcome from task_weeks"
                " where task_id = :id order by week"
            ),
            {"id": task_id},
        )
    )


def row_actions(connection: Connection, task_id: str) -> list[str]:
    """What was done to the task's week rows, as the audit log names it."""
    return list(
        connection.execute(
            text(
                "select action from audit_log where table_name = 'task_weeks'"
                " and new_row ->> 'task_id' = :id order by id"
            ),
            {"id": task_id},
        ).scalars()
    )


def open_next_week(connection: Connection) -> None:
    connection.execute(
        text("update users set planned_through_week = :week where id = :id"),
        {"week": week_of(today()) + timedelta(weeks=1), "id": FIXED_USER_ID},
    )


def one_off(client: TestClient) -> Any:
    return create_goal(
        client, {"type": "oneOff", "label": "Move house", "measurableLine": "Keys handed in"}
    )


# addTask


def test_a_task_with_no_day_goes_to_this_weeks_bank(
    tasks_client: TestClient, connection: Connection
) -> None:
    task_id = uuid4()

    task = add_task(
        tasks_client, task_id, title=" Call the dentist ", timeOfDay={"kind": "by", "time": "18:00"}
    )

    this_week = week_of(today())
    assert task == {
        "id": str(task_id),
        "title": "Call the dentist",
        "origin": "byHand",
        "state": "open",
        "goalId": None,
        "goalLabel": None,
        "recurringItemId": None,
        "dueDate": None,
        "timeOfDay": {"kind": "by", "time": "18:00"},
        "valueLogged": None,
        "completedAt": None,
        "completedOn": None,
        "week": this_week.isoformat(),
        "plannedDay": None,
        "placedByHand": False,
        "carriedOver": 0,
    }
    assert rows(connection, str(task_id)) == [(this_week, None, False, None)]
    assert [row.action for row in audit_rows(connection, task_id)] == ["add task"]


def test_a_task_added_to_a_day_is_placed_by_hand(tasks_client: TestClient) -> None:
    task = add_task(tasks_client, day=today().isoformat())

    assert (task["plannedDay"], task["placedByHand"]) == (today().isoformat(), True)


def test_a_task_can_serve_a_goal(tasks_client: TestClient) -> None:
    goal = create_goal(tasks_client, lifting())

    task = add_task(tasks_client, goalId=goal["id"])

    assert (task["goalId"], task["goalLabel"]) == (goal["id"], "Be strong")


def test_a_past_day_saves_the_task_in_the_bank(tasks_client: TestClient) -> None:
    task = add_task(tasks_client, day=(today() - timedelta(days=1)).isoformat())

    assert (task["week"], task["plannedDay"]) == (week_of(today()).isoformat(), None)


def test_a_due_date_in_an_open_next_week_goes_to_that_weeks_bank(
    tasks_client: TestClient, connection: Connection
) -> None:
    open_next_week(connection)
    next_week = week_of(today()) + timedelta(weeks=1)

    task = add_task(tasks_client, dueDate=(next_week + timedelta(days=2)).isoformat())

    assert (task["week"], task["plannedDay"]) == (next_week.isoformat(), None)


def test_a_due_date_in_a_week_not_open_yet_waits_with_no_row(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client, dueDate=(today() + timedelta(days=8)).isoformat())

    assert task["week"] is None
    assert rows(connection, task["id"]) == []


def test_an_overdue_task_goes_to_this_weeks_bank(tasks_client: TestClient) -> None:
    task = add_task(tasks_client, dueDate=(today() - timedelta(days=10)).isoformat())

    assert task["week"] == week_of(today()).isoformat()


def test_a_one_off_goals_step_with_no_date_waits(
    tasks_client: TestClient, connection: Connection
) -> None:
    step = add_task(tasks_client, goalId=one_off(tasks_client)["id"])

    assert step["week"] is None
    assert rows(connection, step["id"]) == []


def test_the_same_add_twice_returns_the_task_as_it_is(
    tasks_client: TestClient, connection: Connection
) -> None:
    task_id = uuid4()
    first = add_task(tasks_client, task_id)

    again = add_task(tasks_client, task_id, title="Something else", day=today().isoformat())

    assert again == first
    assert [row.action for row in audit_rows(connection, task_id)] == ["add task"]


def test_another_users_goal_is_not_found(tasks_client: TestClient, connection: Connection) -> None:
    theirs = add_goal_for(connection, add_other_user(connection))

    response = tasks_client.put(
        f"/api/tasks/{uuid4()}", json={"title": "Pack", "goalId": str(theirs)}
    )

    assert response.status_code == 404


def test_a_goal_that_isnt_active_gets_no_new_tasks(tasks_client: TestClient) -> None:
    goal = create_goal(tasks_client, lifting())
    tasks_client.post(f"/api/goals/{goal['id']}/pause")

    response = tasks_client.put(
        f"/api/tasks/{uuid4()}", json={"title": "Lift", "goalId": goal["id"]}
    )

    assert response.status_code == 409


@pytest.mark.parametrize(
    "body",
    [
        {"title": "  "},
        {"title": "x" * 201},
        {"title": "a\x00b"},
        {"title": "Run", "timeOfDay": {"kind": "by", "time": "6pm"}},
        {"title": "Run", "timeOfDay": {"kind": "around", "time": "18:00"}},
    ],
)
def test_a_task_that_breaks_the_rules_is_refused(tasks_client: TestClient, body: Any) -> None:
    assert tasks_client.put(f"/api/tasks/{uuid4()}", json=body).status_code == 422


def test_adding_a_task_needs_the_time_zone(client: TestClient) -> None:
    assert client.put(f"/api/tasks/{uuid4()}", json={"title": "Pack"}).status_code == 422


# Where a task lands, for the cases the API can't reach yet: a current week after today's,
# which `week-turnover` brings (after a wrap-up, or a flight west).

SUNDAY = date(2026, 11, 22)
AFTER_WRAP_UP = OpenWeeks(current=date(2026, 11, 23), next_open=False)


def test_today_before_the_current_week_puts_a_task_for_today_in_the_bank() -> None:
    new = NewTask(title="Pack", day=SUNDAY)

    assert landing(new, None, SUNDAY, AFTER_WRAP_UP) == Landing(date(2026, 11, 23))


def test_today_before_the_current_week_still_allows_its_days() -> None:
    new = NewTask(title="Pack", day=date(2026, 11, 24))

    assert landing(new, None, SUNDAY, AFTER_WRAP_UP) == Landing(
        date(2026, 11, 23), date(2026, 11, 24)
    )


def test_a_day_in_a_week_not_open_yet_puts_the_task_in_the_current_bank() -> None:
    new = NewTask(title="Pack", day=date(2026, 12, 2))

    assert landing(new, None, SUNDAY, AFTER_WRAP_UP) == Landing(date(2026, 11, 23))


# updateTask


def test_an_edit_changes_what_was_typed_and_leaves_the_task_where_it_is(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(
        tasks_client, day=today().isoformat(), timeOfDay={"kind": "at", "time": "09:30"}
    )
    due = (today() + timedelta(days=20)).isoformat()

    response = tasks_client.patch(
        f"/api/tasks/{task['id']}", json={"title": "Call the vet", "dueDate": due}
    )

    assert response.status_code == 200, response.text
    assert response.json() == task | {"title": "Call the vet", "dueDate": due, "timeOfDay": None}
    assert [row.action for row in audit_rows(connection, task["id"])] == ["add task", "update task"]


def test_an_edit_of_another_users_task_is_not_found(
    tasks_client: TestClient, connection: Connection
) -> None:
    theirs = add_task_for(connection, add_other_user(connection))

    response = tasks_client.patch(f"/api/tasks/{theirs}", json={"title": "Mine now"})

    assert response.status_code == 404


def test_an_edit_with_a_blank_title_is_refused(tasks_client: TestClient) -> None:
    task = add_task(tasks_client)

    assert tasks_client.patch(f"/api/tasks/{task['id']}", json={"title": " "}).status_code == 422
