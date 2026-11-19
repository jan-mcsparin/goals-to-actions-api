"""Closing a week: each unfinished task's ending, and when it happens (spec `week-turnover`)."""

from collections.abc import Iterator
from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.config import FIXED_USER_ID
from app.turnover.rules import catch_up
from tests.test_goals import ZONE

W1 = date(2026, 11, 2)
W2 = date(2026, 11, 9)
W3 = date(2026, 11, 16)
W4 = date(2026, 11, 23)


def at(day: date, hour: int = 12) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=ZoneInfo(ZONE))


@pytest.fixture
def tasks_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


def new_task(
    connection: Connection,
    week: date,
    *,
    origin: str = "by_hand",
    goal_id: UUID | None = None,
    item_id: UUID | None = None,
    period_start: date | None = None,
    outcome: str | None = None,
    number: int = 1,
) -> UUID:
    task_id = uuid4()
    connection.execute(
        text(
            "insert into tasks (id, user_id, title, origin, goal_id, recurring_item_id,"
            " period_start, number, state)"
            " values (:id, :user, 'Thing', :origin, :goal, :item, :period, :number, 'open')"
        ),
        {
            "id": task_id,
            "user": FIXED_USER_ID,
            "origin": origin,
            "goal": goal_id,
            "item": item_id,
            "period": period_start if origin != "by_hand" else None,
            "number": number if origin != "by_hand" else None,
        },
    )
    connection.execute(
        text(
            "insert into task_weeks (id, user_id, task_id, week, outcome)"
            " values (gen_random_uuid(), :user, :task, :week, :outcome)"
        ),
        {"user": FIXED_USER_ID, "task": task_id, "week": week, "outcome": outcome},
    )
    return task_id


def new_goal(connection: Connection) -> UUID:
    goal_id = uuid4()
    connection.execute(
        text(
            "insert into goals (id, user_id, type, label, measurable_line, start_date)"
            " values (:id, :user, 'building', 'Be strong', 'Lift', '2026-10-01')"
        ),
        {"id": goal_id, "user": FIXED_USER_ID},
    )
    connection.execute(
        text(
            "insert into weekly_targets"
            " (id, user_id, goal_id, kind, sessions, unit, effective_from)"
            " values (gen_random_uuid(), :user, :goal, 'count', 3, 'runs', '2026-10-26')"
        ),
        {"user": FIXED_USER_ID, "goal": goal_id},
    )
    return goal_id


def new_item(connection: Connection, **fields: Any) -> UUID:
    item_id = uuid4()
    schedule = {"schedule_kind": "weekly", "weekday": 2, "times": None, "period": None} | fields
    connection.execute(
        text(
            "insert into recurring_items (id, user_id, name, schedule_kind, weekday, times,"
            " period, starts_on) values (:id, :user, 'Item', :schedule_kind, :weekday, :times,"
            " :period, '2026-10-01')"
        ),
        {"id": item_id, "user": FIXED_USER_ID} | schedule,
    )
    return item_id


def state(connection: Connection, task_id: UUID) -> str:
    return str(
        connection.execute(
            text("select state from tasks where id = :id"), {"id": task_id}
        ).scalar_one()
    )


def history(connection: Connection, task_id: UUID) -> list[tuple[date, str | None]]:
    return [
        (row.week, row.outcome)
        for row in connection.execute(
            text(
                "select week, outcome from task_weeks where task_id = :id order by week, created_at"
            ),
            {"id": task_id},
        )
    ]


def close_on(connection: Connection, day: date, hour: int = 12) -> None:
    catch_up(connection, FIXED_USER_ID, at(day, hour))


def test_a_task_added_by_hand_rolls_over_into_the_bank(connection: Connection) -> None:
    task = new_task(connection, W2)

    close_on(connection, date(2026, 11, 18))

    assert history(connection, task) == [(W2, "rolled_over"), (W3, None)]
    assert state(connection, task) == "open"


def test_a_weekly_target_session_lapses(connection: Connection) -> None:
    task = new_task(
        connection, W2, origin="weekly_target", goal_id=new_goal(connection), period_start=W2
    )

    close_on(connection, date(2026, 11, 18))

    assert history(connection, task)[0] == (W2, "lapsed")
    assert state(connection, task) == "lapsed"


def test_a_fixed_day_task_rolls_over(connection: Connection) -> None:
    item = new_item(connection)
    task = new_task(connection, W2, origin="recurring_item", item_id=item, period_start=W2)

    close_on(connection, date(2026, 11, 18))

    assert history(connection, task) == [(W2, "rolled_over"), (W3, None)]


def test_a_flexible_task_carries_inside_its_period_and_lapses_at_its_end(
    connection: Connection,
) -> None:
    item = new_item(connection, schedule_kind="flexible", weekday=None, times=1, period="two_weeks")
    connection.execute(text("update recurring_items set starts_on = '2026-11-02'"))
    task = new_task(connection, W1, origin="recurring_item", item_id=item, period_start=W1)

    close_on(connection, date(2026, 11, 11))  # current week: Nov 9, the period's second week
    assert history(connection, task) == [(W1, "rolled_over"), (W2, None)]

    close_on(connection, date(2026, 11, 18))
    assert history(connection, task)[1] == (W2, "lapsed")
    assert state(connection, task) == "lapsed"


def test_a_set_aside_generated_task_ends_with_its_week_and_still_reads_set_aside(
    connection: Connection,
) -> None:
    task = new_task(
        connection,
        W2,
        origin="weekly_target",
        goal_id=new_goal(connection),
        period_start=W2,
        outcome="set_aside",
    )

    close_on(connection, date(2026, 11, 18))

    assert history(connection, task) == [(W2, "set_aside")]
    assert state(connection, task) == "lapsed"


def test_a_set_aside_task_added_by_hand_waits(connection: Connection) -> None:
    task = new_task(connection, W2, outcome="set_aside")

    close_on(connection, date(2026, 11, 18))

    assert history(connection, task) == [(W2, "set_aside")]
    assert state(connection, task) == "open"


def test_a_week_of_one_of_three_is_followed_by_a_week_of_three(connection: Connection) -> None:
    goal = new_goal(connection)
    for number in (1, 2, 3):
        new_task(
            connection,
            W2,
            origin="weekly_target",
            goal_id=goal,
            period_start=W2,
            number=number,
            outcome="done" if number == 1 else None,
        )
    connection.execute(
        text(
            "update tasks set state = 'done', completed_at = now(), completed_on = '2026-11-10'"
            " where id in (select task_id from task_weeks where outcome = 'done')"
        )
    )

    close_on(connection, date(2026, 11, 18))

    count = connection.execute(
        text(
            "select count(*) from tasks where goal_id = :g and period_start = :w and state = 'open'"
        ),
        {"g": goal, "w": W3},
    ).scalar_one()
    assert count == 3


def test_opened_on_sunday_evening_and_closed_on_monday_the_carry_overs_arrive_then(
    connection: Connection,
) -> None:
    task = new_task(connection, W3)
    connection.execute(
        text(
            "update users set planned_through_week = '2026-11-23',"
            " closed_through_week = '2026-11-09'"
        )
    )

    assert not catch_up(connection, FIXED_USER_ID, at(date(2026, 11, 22), 19))
    assert history(connection, task) == [(W3, None)]

    close_on(connection, W4, 8)

    assert history(connection, task) == [(W3, "rolled_over"), (W4, None)]


def test_three_weeks_away_the_weeks_with_rows_close_and_a_task_carries_once(
    connection: Connection,
) -> None:
    task = new_task(connection, W1)
    goal = new_goal(connection)
    session = new_task(connection, W2, origin="weekly_target", goal_id=goal, period_start=W2)

    close_on(connection, date(2026, 11, 25))

    assert history(connection, task) == [(W1, "rolled_over"), (W4, None)]
    assert history(connection, session) == [(W2, "lapsed")]
    weeks_with_rows = connection.execute(
        text("select distinct week from task_weeks where week < :w4 and outcome is null"),
        {"w4": W4},
    ).all()
    assert weeks_with_rows == []


def test_closing_twice_changes_nothing(connection: Connection) -> None:
    task = new_task(connection, W2)
    close_on(connection, date(2026, 11, 18))

    close_on(connection, date(2026, 11, 18))

    assert history(connection, task) == [(W2, "rolled_over"), (W3, None)]


def test_a_request_closes_the_week_and_is_audited(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = new_task(connection, W2)

    assert tasks_client.get(f"/api/weeks/{W3}").status_code == 200

    assert history(connection, task) == [(W2, "rolled_over"), (W3, None)]
    assert "close week" in [
        row.action
        for row in connection.execute(
            text("select action from audit_log where table_name = 'task_weeks'")
        )
    ]


def test_a_check_off_dated_sunday_and_sent_after_the_close_is_done_not_lapsed(
    tasks_client: TestClient, connection: Connection
) -> None:
    goal = new_goal(connection)
    session = new_task(connection, W2, origin="weekly_target", goal_id=goal, period_start=W2)
    tasks_client.get(f"/api/weeks/{W3}")  # closes the week: the session lapses
    assert state(connection, session) == "lapsed"

    response = tasks_client.post(
        f"/api/tasks/{session}/check-off",
        json={"completedAt": "2026-11-15T23:00:00Z", "completedOn": "2026-11-15"},
    )

    assert response.status_code == 200, response.text
    assert state(connection, session) == "done"
    assert history(connection, session) == [(W2, "done")]


def test_a_late_uncheck_follows_the_closing_rule(
    tasks_client: TestClient, connection: Connection
) -> None:
    fixed = new_item(connection)
    rolls = new_task(
        connection, W2, origin="recurring_item", item_id=fixed, period_start=W2, outcome="done"
    )
    goal = new_goal(connection)
    lapses = new_task(
        connection, W2, origin="weekly_target", goal_id=goal, period_start=W2, outcome="done"
    )
    done_at = "2026-11-10T08:00:00Z"
    for task in (rolls, lapses):
        connection.execute(
            text(
                "update tasks set state = 'done', completed_at = :at, completed_on = '2026-11-10'"
                " where id = :id"
            ),
            {"at": done_at, "id": task},
        )

    for task in (rolls, lapses):
        assert tasks_client.post(f"/api/tasks/{task}/uncheck").status_code == 200

    assert history(connection, rolls) == [(W2, "rolled_over"), (W3, None)]
    assert history(connection, lapses) == [(W2, "lapsed")]
    assert state(connection, lapses) == "lapsed"
