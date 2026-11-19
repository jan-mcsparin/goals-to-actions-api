"""Opening a week: what fills its bank, and when (spec `week-turnover`)."""

from collections.abc import Iterator
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.config import FIXED_USER_ID
from app.turnover.rules import catch_up
from tests.conftest import FixedClock
from tests.test_goals import ZONE, create_goal, lifting
from tests.test_recurring_items import create as create_item
from tests.test_recurring_items import item

WEEK = date(2026, 11, 16)
NEXT_WEEK = date(2026, 11, 23)


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZoneInfo(ZONE))


def reset_markers(connection: Connection, planned: date | None = None) -> None:
    connection.execute(
        text("update users set planned_through_week = :week where id = :id"),
        {"week": planned, "id": FIXED_USER_ID},
    )


def rows(connection: Connection, week: date) -> list[Any]:
    return list(
        connection.execute(
            text(
                "select tasks.title, tasks.origin, tasks.period_start, tasks.number,"
                " task_weeks.planned_day"
                " from task_weeks join tasks on tasks.id = task_weeks.task_id"
                " where task_weeks.week = :week order by tasks.title, tasks.number"
            ),
            {"week": week},
        )
    )


def audit_actions(connection: Connection) -> list[str]:
    return [
        row.action
        for row in connection.execute(
            text("select action from audit_log where table_name = 'users' order by id")
        )
    ]


@pytest.fixture
def goals_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


@pytest.fixture
def work(goals_client: TestClient, connection: Connection) -> Connection:
    """A lifting goal (3 a week) and a flexible item (2 a week), made on the pinned Wednesday,
    then the markers cleared so the week is open to be opened."""
    create_goal(goals_client, lifting())
    create_item(
        goals_client,
        item(
            name="Stretch",
            schedule={"kind": "flexible", "times": 2, "period": "week"},
            startsOn="2026-11-16",
        ),
    )
    reset_markers(connection)
    return connection


def test_the_first_request_in_a_week_opens_it(work: Connection) -> None:
    assert catch_up(work, FIXED_USER_ID, at(date(2026, 11, 18), 12))

    titles = [(row.title, row.number) for row in rows(work, WEEK)]
    assert titles == [
        ("Be strong", 1),
        ("Be strong", 2),
        ("Be strong", 3),
        ("Stretch", 1),
        ("Stretch", 2),
    ]
    assert all(row.planned_day is None for row in rows(work, WEEK))
    assert rows(work, NEXT_WEEK) == []


def test_next_week_opens_at_6pm_on_sunday_and_not_before(work: Connection) -> None:
    catch_up(work, FIXED_USER_ID, at(date(2026, 11, 18), 12))
    sunday = date(2026, 11, 22)
    before = rows(work, WEEK)

    assert not catch_up(work, FIXED_USER_ID, at(sunday, 17, 59))
    assert rows(work, NEXT_WEEK) == []

    assert catch_up(work, FIXED_USER_ID, at(sunday, 18))
    assert len(rows(work, NEXT_WEEK)) == 5
    assert rows(work, WEEK) == before


def test_opening_twice_makes_nothing_new(work: Connection) -> None:
    sunday_evening = at(date(2026, 11, 22), 19)
    catch_up(work, FIXED_USER_ID, sunday_evening)
    assert not catch_up(work, FIXED_USER_ID, sunday_evening)
    # Sunday evening is the last day of this week, so it has one of each; next week is full.
    assert len(rows(work, WEEK)) == 2 and len(rows(work, NEXT_WEEK)) == 5

    # Even with the marker lost, the unique keys and the existing check make nothing twice.
    reset_markers(work)
    catch_up(work, FIXED_USER_ID, sunday_evening)
    assert len(rows(work, WEEK)) == 2 and len(rows(work, NEXT_WEEK)) == 5


def test_a_paused_goal_and_an_item_turned_off_get_nothing(
    work: Connection, goals_client: TestClient
) -> None:
    work.execute(text("update goals set status = 'paused'"))
    work.execute(text("update recurring_items set active = false"))

    catch_up(work, FIXED_USER_ID, at(date(2026, 11, 18), 12))

    assert rows(work, WEEK) == []


def test_a_goal_started_on_saturday_gets_two_sessions(work: Connection) -> None:
    work.execute(text("update goals set start_date = '2026-11-21'"))

    catch_up(work, FIXED_USER_ID, at(date(2026, 11, 21), 9))

    assert [row.number for row in rows(work, WEEK) if row.title == "Be strong"] == [1, 2]


def test_a_task_now_due_gets_a_row_in_the_bank(work: Connection) -> None:
    work.execute(
        text(
            "insert into tasks (id, user_id, title, origin, due_date)"
            " values (gen_random_uuid(), :id, 'Renew passport', 'by_hand', '2026-11-25')"
        ),
        {"id": FIXED_USER_ID},
    )

    catch_up(work, FIXED_USER_ID, at(date(2026, 11, 22), 19))

    assert "Renew passport" not in [row.title for row in rows(work, WEEK)]
    assert "Renew passport" in [row.title for row in rows(work, NEXT_WEEK)]


def test_a_request_opens_the_week_and_is_audited(
    work: Connection, goals_client: TestClient
) -> None:
    response = goals_client.get(f"/api/weeks/{WEEK}")

    assert response.status_code == 200
    assert len(rows(work, WEEK)) == 5
    assert "open week" in [
        row.action
        for row in work.execute(text("select action from audit_log where action = 'open week'"))
    ]


def test_a_request_with_nothing_due_writes_nothing(
    work: Connection, goals_client: TestClient, fixed_clock: FixedClock
) -> None:
    goals_client.get(f"/api/weeks/{WEEK}")
    count = work.execute(text("select count(*) from audit_log")).scalar_one()

    assert goals_client.get(f"/api/weeks/{WEEK}").status_code == 200

    assert work.execute(text("select count(*) from audit_log")).scalar_one() == count
