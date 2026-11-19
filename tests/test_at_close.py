"""What closing a week will do to a task (`atClose`), "Still matter?" (`stillMatters`), and the
upcoming list."""

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.config import FIXED_USER_ID
from tests.conftest import FixedClock
from tests.test_aspirations import add_other_user
from tests.test_close_week import W1, W2, W3, history, new_goal, new_item, new_task, state
from tests.test_goals import ZONE

TUESDAY = datetime(2026, 11, 10, 19, 0, tzinfo=UTC)  # in the week of W2


def read(client: TestClient, week: date) -> dict[str, Any]:
    response = client.get(f"/api/weeks/{week}")
    assert response.status_code == 200, response.text
    return {task["id"]: task for task in response.json()["tasks"]}


def test_at_close_agrees_with_what_closing_then_does(
    client: TestClient, fixed_clock: FixedClock, connection: Connection
) -> None:
    client.headers["X-Time-Zone"] = ZONE
    goal = new_goal(connection)
    fixed = new_item(connection)
    weekly_flexible = new_item(
        connection, schedule_kind="flexible", weekday=None, times=2, period="week"
    )
    two_weeks = new_item(
        connection, schedule_kind="flexible", weekday=None, times=1, period="two_weeks"
    )
    monthly_flexible = new_item(
        connection, schedule_kind="flexible", weekday=None, times=1, period="month"
    )
    cases = {
        "by hand": new_task(connection, W2),
        "weekly target": new_task(
            connection, W2, origin="weekly_target", goal_id=goal, period_start=W2, number=9
        ),
        "fixed day": new_task(
            connection, W2, origin="recurring_item", item_id=fixed, period_start=W2
        ),
        "flexible, a week": new_task(
            connection, W2, origin="recurring_item", item_id=weekly_flexible, period_start=W2
        ),
        "flexible, first of two weeks": new_task(
            connection, W2, origin="recurring_item", item_id=two_weeks, period_start=W2
        ),
        "flexible, inside a month": new_task(
            connection,
            W2,
            origin="recurring_item",
            item_id=monthly_flexible,
            period_start=date(2026, 11, 2),
        ),
        "flexible, last of two weeks": new_task(
            connection, W3, origin="recurring_item", item_id=two_weeks, period_start=W2, number=2
        ),
    }
    fixed_clock.instant = TUESDAY
    week_two = read(client, W2)
    expected = {
        "by hand": "carriesOver",
        "weekly target": "ends",
        "fixed day": "carriesOver",
        "flexible, a week": "ends",
        "flexible, first of two weeks": "carriesOver",
        "flexible, inside a month": "carriesOver",
    }
    for name, answer in expected.items():
        assert week_two[str(cases[name])]["atClose"] == answer, name

    fixed_clock.instant = datetime(2026, 11, 18, 19, 0, tzinfo=UTC)  # the week of W3
    week_three = read(client, W3)  # closes W2

    assert week_three[str(cases["flexible, last of two weeks"])]["atClose"] == "ends"
    for name, answer in expected.items():
        rows = history(connection, cases[name])
        closed = rows[0][1]
        assert closed == ("rolled_over" if answer == "carriesOver" else "lapsed"), name
    assert state(connection, cases["weekly target"]) == "lapsed"


def test_a_set_aside_task_is_not_on_the_week_read(
    client: TestClient, fixed_clock: FixedClock, connection: Connection
) -> None:
    client.headers["X-Time-Zone"] = ZONE
    fixed_clock.instant = TUESDAY
    task = new_task(connection, W2, outcome="set_aside")

    assert str(task) not in read(client, W2)  # set-aside rows aren't on the week read


def add_rolled_rows(connection: Connection, task_id: UUID, weeks: list[date]) -> None:
    for week in weeks:
        connection.execute(
            text(
                "insert into task_weeks (id, user_id, task_id, week, outcome)"
                " values (gen_random_uuid(), :user, :task, :week, 'rolled_over')"
            ),
            {"user": FIXED_USER_ID, "task": task_id, "week": week},
        )


def test_a_task_rolled_over_twice_is_asked_about(
    client: TestClient, connection: Connection
) -> None:
    client.headers["X-Time-Zone"] = ZONE
    task = new_task(connection, W3)  # in play in the current week
    add_rolled_rows(connection, task, [W1, W2])

    week = read(client, W3)

    assert week[str(task)]["stillMatters"] is True
    assert week[str(task)]["carriedOver"] == 2


def test_a_task_rolled_over_once_is_not_asked_about(
    client: TestClient, connection: Connection
) -> None:
    client.headers["X-Time-Zone"] = ZONE
    task = new_task(connection, W3)
    add_rolled_rows(connection, task, [W2])

    assert read(client, W3)[str(task)]["stillMatters"] is False


def test_a_fixed_day_task_is_asked_about_but_a_flexible_one_carrying_in_its_period_never(
    client: TestClient, connection: Connection
) -> None:
    client.headers["X-Time-Zone"] = ZONE
    fixed = new_task(
        connection, W3, origin="recurring_item", item_id=new_item(connection), period_start=W1
    )
    add_rolled_rows(connection, fixed, [W1, W2])
    flexible = new_task(
        connection,
        W3,
        origin="recurring_item",
        item_id=new_item(
            connection, schedule_kind="flexible", weekday=None, times=1, period="month"
        ),
        period_start=date(2026, 11, 2),
    )
    add_rolled_rows(connection, flexible, [W1, W2])

    week = read(client, W3)

    assert week[str(fixed)]["stillMatters"] is True
    assert week[str(flexible)]["stillMatters"] is False


def test_after_an_answer_it_waits_for_two_more_rollovers(
    client: TestClient, connection: Connection
) -> None:
    client.headers["X-Time-Zone"] = ZONE
    task = new_task(connection, W3)
    add_rolled_rows(connection, task, [W1, W2])
    connection.execute(
        text("update tasks set still_matters_answered_on = :day where id = :id"),
        {"day": W2 + timedelta(days=2), "id": task},
    )

    assert read(client, W3)[str(task)]["stillMatters"] is False  # only W2's rollover counts


def add_task(client: TestClient, **body: Any) -> Any:
    response = client.put(f"/api/tasks/{uuid4()}", json={"title": "Renew passport"} | body)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_upcoming_list_holds_waiting_tasks_by_due_date(client: TestClient) -> None:
    client.headers["X-Time-Zone"] = ZONE
    later = add_task(client, title="Later", dueDate="2027-03-01")
    sooner = add_task(client, title="Sooner", dueDate="2027-01-01")
    add_task(client, title="No date")
    add_task(client, title="Placed", dueDate="2027-01-02", day="2026-11-19")

    response = client.get("/api/tasks/upcoming")

    assert response.status_code == 200
    assert [task["id"] for task in response.json()["tasks"]] == [sooner["id"], later["id"]]
    assert response.json()["tasks"][0]["week"] is None


def test_the_upcoming_list_leaves_out_another_owners_tasks(
    client: TestClient, connection: Connection
) -> None:
    client.headers["X-Time-Zone"] = ZONE
    other = add_other_user(connection)
    connection.execute(
        text(
            "insert into tasks (id, user_id, title, origin, due_date)"
            " values (gen_random_uuid(), :user, 'Theirs', 'by_hand', '2027-01-01')"
        ),
        {"user": other},
    )

    assert client.get("/api/tasks/upcoming").json() == {"tasks": []}
