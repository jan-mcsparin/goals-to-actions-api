from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.weeks import week_of
from tests.test_aspirations import add_other_user, audit_rows
from tests.test_goals import ZONE, create_goal, lifting, today
from tests.test_tasks import add_task, add_task_for, one_off, open_next_week, rows


@pytest.fixture
def tasks_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


def done_on(day: str, **more: Any) -> dict[str, Any]:
    return {"completedAt": f"{day}T07:30:00Z", "completedOn": day} | more


def check_off(client: TestClient, task_id: str, **body: Any) -> Any:
    response = client.post(
        f"/api/tasks/{task_id}/check-off", json=done_on(today().isoformat()) | body
    )
    assert response.status_code == 200, response.text
    return response.json()


def uncheck(client: TestClient, task_id: str) -> Any:
    response = client.post(f"/api/tasks/{task_id}/uncheck")
    assert response.status_code == 200, response.text
    return response.json()


def test_a_check_off_marks_the_task_and_its_row_done(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client, day=today().isoformat())

    done = check_off(tasks_client, task["id"], valueLogged=3.1)

    assert done == task | {
        "state": "done",
        "completedAt": f"{today().isoformat()}T07:30:00Z",
        "completedOn": today().isoformat(),
        "valueLogged": 3.1,
        "atClose": None,
    }
    assert rows(connection, task["id"]) == [(week_of(today()), today(), True, "done")]
    assert [row.action for row in audit_rows(connection, task["id"])] == [
        "add task",
        "check off task",
    ]


def test_a_check_off_after_midnight_counts_for_the_day_the_phone_sent(
    tasks_client: TestClient,
) -> None:
    # 12:30 a.m. in Tokyo is still the day before in UTC.
    task = add_task(tasks_client)
    the_evening_before = (today() - timedelta(days=1)).isoformat()

    done = check_off(
        tasks_client,
        task["id"],
        completedAt=f"{the_evening_before}T15:30:00Z",
        completedOn=today().isoformat(),
    )

    assert done["completedOn"] == today().isoformat()


def test_a_bank_task_checked_off_stays_off_the_days(tasks_client: TestClient) -> None:
    task = add_task(tasks_client)

    assert check_off(tasks_client, task["id"])["plannedDay"] is None


def test_the_same_check_off_twice_changes_nothing_more(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client)
    first = check_off(tasks_client, task["id"])

    assert check_off(tasks_client, task["id"]) == first
    assert len(rows(connection, task["id"])) == 1


def test_a_waiting_step_checked_off_gets_a_done_row_on_that_day(
    tasks_client: TestClient, connection: Connection
) -> None:
    step = add_task(tasks_client, goalId=one_off(tasks_client)["id"])
    yesterday = today() - timedelta(days=1)

    done = check_off(tasks_client, step["id"], **done_on(yesterday.isoformat()))

    assert (done["week"], done["plannedDay"]) == (
        week_of(yesterday).isoformat(),
        yesterday.isoformat(),
    )
    assert rows(connection, step["id"]) == [(week_of(yesterday), yesterday, False, "done")]


def test_unchecking_a_waiting_step_leaves_it_on_the_day_it_was_done(
    tasks_client: TestClient, connection: Connection
) -> None:
    step = add_task(tasks_client, goalId=one_off(tasks_client)["id"])
    check_off(tasks_client, step["id"])

    unchecked = uncheck(tasks_client, step["id"])

    assert (unchecked["state"], unchecked["plannedDay"]) == ("open", today().isoformat())
    assert rows(connection, step["id"]) == [(week_of(today()), today(), False, None)]


def test_next_weeks_tasks_cannot_be_checked_off_yet(
    tasks_client: TestClient, connection: Connection
) -> None:
    open_next_week(connection)
    next_monday = week_of(today()) + timedelta(weeks=1)
    task = add_task(tasks_client, dueDate=next_monday.isoformat())

    response = tasks_client.post(
        f"/api/tasks/{task['id']}/check-off", json=done_on(today().isoformat())
    )

    assert response.status_code == 409


def test_a_dropped_task_cannot_be_checked_off(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client)
    connection.execute(
        text("update task_weeks set outcome = 'dropped' where task_id = :id"), {"id": task["id"]}
    )
    connection.execute(
        text("update tasks set state = 'dropped' where id = :id"), {"id": task["id"]}
    )

    response = tasks_client.post(
        f"/api/tasks/{task['id']}/check-off", json=done_on(today().isoformat())
    )

    assert response.status_code == 409


def test_another_users_task_is_not_found(tasks_client: TestClient, connection: Connection) -> None:
    theirs = add_task_for(connection, add_other_user(connection))

    assert (
        tasks_client.post(f"/api/tasks/{theirs}/check-off", json=done_on("2026-11-18")).status_code
        == 404
    )
    assert tasks_client.post(f"/api/tasks/{theirs}/uncheck").status_code == 404
    assert tasks_client.post(f"/api/tasks/{uuid4()}/uncheck").status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"completedOn": "2026-11-18"},
        {"completedAt": "2026-11-18T07:30:00", "completedOn": "2026-11-18"},
        done_on("2026-11-18", valueLogged=-1),
    ],
)
def test_a_check_off_needs_an_aware_moment_and_a_value_not_below_zero(
    tasks_client: TestClient, body: Any
) -> None:
    task = add_task(tasks_client)

    assert tasks_client.post(f"/api/tasks/{task['id']}/check-off", json=body).status_code == 422


# uncheckTask


def test_check_off_then_uncheck_leaves_the_task_as_it_was(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client, day=today().isoformat())
    check_off(tasks_client, task["id"], valueLogged=5)

    assert uncheck(tasks_client, task["id"]) == task
    assert rows(connection, task["id"]) == [(week_of(today()), today(), True, None)]


def test_the_same_uncheck_twice_changes_nothing_more(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client)
    check_off(tasks_client, task["id"])
    uncheck(tasks_client, task["id"])

    assert uncheck(tasks_client, task["id"]) == task
    assert [row.action for row in audit_rows(connection, task["id"])] == [
        "add task",
        "check off task",
        "uncheck task",
    ]


# Check-offs and unchecks that arrive after their week closed. Nothing closes a week until
# `week-turnover`, so these tests write the closed rows themselves.


def last_week() -> Any:
    return week_of(today()) - timedelta(weeks=1)


def last_sunday() -> str:
    return (week_of(today()) - timedelta(days=1)).isoformat()


def closed_session(connection: Connection, goal_id: str, state: str, outcome: str) -> str:
    """A weekly-target task whose week has closed."""
    task_id = str(uuid4())
    done = state == "done"
    connection.execute(
        text(
            "insert into tasks (id, user_id, title, origin, goal_id, state, period_start, number,"
            " completed_at, completed_on)"
            " select :id, user_id, 'Lift', 'weekly_target', id, :state, :week, 1,"
            " case when :done then now() end, case when :done then cast(:sunday as date) end"
            " from goals where id = :goal"
        ),
        {
            "id": task_id,
            "goal": goal_id,
            "state": state,
            "week": last_week(),
            "done": done,
            "sunday": last_sunday(),
        },
    )
    add_closed_row(connection, task_id, last_week(), outcome)
    return task_id


def add_closed_row(connection: Connection, task_id: str, week: Any, outcome: str | None) -> None:
    connection.execute(
        text(
            "insert into task_weeks (id, user_id, task_id, week, outcome)"
            " select :id, user_id, id, :week, :outcome from tasks where id = :task"
        ),
        {"id": uuid4(), "task": task_id, "week": week, "outcome": outcome},
    )


def test_a_late_check_off_turns_a_lapsed_task_and_its_row_to_done(
    tasks_client: TestClient, connection: Connection
) -> None:
    goal = create_goal(tasks_client, lifting())
    task_id = closed_session(connection, goal["id"], "lapsed", "lapsed")

    done = check_off(tasks_client, task_id, **done_on(last_sunday()))

    assert (done["state"], done["completedOn"], done["week"]) == (
        "done",
        last_sunday(),
        last_week().isoformat(),
    )
    assert rows(connection, task_id) == [(last_week(), None, False, "done")]


def test_a_late_check_off_of_a_task_that_rolled_over_lands_on_its_new_row(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client)
    add_closed_row(connection, task["id"], last_week(), "rolled_over")

    done = check_off(tasks_client, task["id"], **done_on(last_sunday()))

    assert (done["completedOn"], done["week"]) == (last_sunday(), week_of(today()).isoformat())
    assert rows(connection, task["id"]) == [
        (last_week(), None, False, "rolled_over"),
        (week_of(today()), None, False, "done"),
    ]


def test_a_late_uncheck_rolls_a_task_added_by_hand_into_this_weeks_bank(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client)
    connection.execute(
        text("update task_weeks set week = :week where task_id = :id"),
        {"week": last_week(), "id": task["id"]},
    )
    check_off(tasks_client, task["id"], **done_on(last_sunday()))

    unchecked = uncheck(tasks_client, task["id"])

    assert (unchecked["state"], unchecked["week"], unchecked["carriedOver"]) == (
        "open",
        week_of(today()).isoformat(),
        1,
    )
    assert rows(connection, task["id"]) == [
        (last_week(), None, False, "rolled_over"),
        (week_of(today()), None, False, None),
    ]
    assert uncheck(tasks_client, task["id"]) == unchecked


def test_a_late_uncheck_lapses_a_weekly_target_task(
    tasks_client: TestClient, connection: Connection
) -> None:
    goal = create_goal(tasks_client, lifting())
    task_id = closed_session(connection, goal["id"], "done", "done")

    unchecked = uncheck(tasks_client, task_id)

    assert (unchecked["state"], unchecked["completedOn"], unchecked["week"]) == (
        "lapsed",
        None,
        None,
    )
    assert rows(connection, task_id) == [(last_week(), None, False, "lapsed")]


def test_a_set_aside_task_whose_row_is_in_next_week_is_done_on_that_row(
    tasks_client: TestClient, connection: Connection
) -> None:
    # Checked off on a paused goal's page while next week is open.
    open_next_week(connection)
    next_monday = week_of(today()) + timedelta(weeks=1)
    goal = one_off(tasks_client)
    step = add_task(tasks_client, goalId=goal["id"], dueDate=next_monday.isoformat())
    tasks_client.post(f"/api/goals/{goal['id']}/pause")

    done = check_off(tasks_client, step["id"])

    assert (done["state"], done["completedOn"]) == ("done", today().isoformat())
    assert rows(connection, step["id"]) == [(next_monday, None, False, "done")]


def test_a_late_uncheck_under_a_paused_goal_comes_back_set_aside(
    tasks_client: TestClient, connection: Connection
) -> None:
    goal = one_off(tasks_client)
    step = add_task(tasks_client, goalId=goal["id"], dueDate=today().isoformat())
    connection.execute(
        text("update task_weeks set week = :week where task_id = :id"),
        {"week": last_week(), "id": step["id"]},
    )
    check_off(tasks_client, step["id"], **done_on(last_sunday()))
    tasks_client.post(f"/api/goals/{goal['id']}/pause")

    unchecked = uncheck(tasks_client, step["id"])

    assert (unchecked["state"], unchecked["week"]) == ("open", None)
    assert rows(connection, step["id"]) == [
        (last_week(), None, False, "rolled_over"),
        (week_of(today()), None, False, "set_aside"),
    ]


def test_an_uncheck_under_a_paused_goal_stays_set_aside_on_its_day(
    tasks_client: TestClient, connection: Connection
) -> None:
    goal_id = create_goal(tasks_client, lifting())["id"]
    task = add_task(tasks_client, goalId=goal_id, day=today().isoformat())
    check_off(tasks_client, task["id"])
    tasks_client.post(f"/api/goals/{goal_id}/pause")

    unchecked = uncheck(tasks_client, task["id"])

    assert (unchecked["state"], unchecked["week"]) == ("open", None)
    assert rows(connection, task["id"]) == [(week_of(today()), today(), True, "set_aside")]
    tasks_client.post(f"/api/goals/{goal_id}/resume")
    assert rows(connection, task["id"]) == [(week_of(today()), None, False, None)]
