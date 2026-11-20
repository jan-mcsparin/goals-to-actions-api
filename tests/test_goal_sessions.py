"""A goal's sessions in the open weeks: made when the goal comes, when its target is raised
or it returns, and removed when its target is lowered (spec `week-turnover`)."""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from tests.conftest import FixedClock
from tests.test_check_off import check_off
from tests.test_goals import ZONE, create_goal, lifting
from tests.test_task_moves import place

WEEK = date(2026, 11, 16)
NEXT_WEEK = date(2026, 11, 23)
SATURDAY = datetime(2026, 11, 21, 17, 0, tzinfo=UTC)  # 10 a.m. in Denver
SUNDAY_EVENING = datetime(2026, 11, 23, 2, 0, tzinfo=UTC)  # 7 p.m. Sunday 22 Nov


@pytest.fixture
def tasks_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


def sessions(client: TestClient, week: date) -> list[Any]:
    tasks = client.get(f"/api/weeks/{week}").json()["tasks"]
    return [task for task in tasks if task["origin"] == "weeklyTarget"]


def set_target(client: TestClient, goal_id: str, sessions: int) -> None:
    response = client.put(
        f"/api/goals/{goal_id}/weekly-target",
        json={"kind": "count", "sessions": sessions, "unit": "lifting sessions"},
    )
    assert response.status_code == 200, response.text


def test_a_goal_made_midweek_has_its_sessions_placed_from_tomorrow(
    tasks_client: TestClient,
) -> None:
    create_goal(tasks_client, lifting())

    found = sessions(tasks_client, WEEK)

    # Made on Wednesday: three sessions over Thursday to Sunday, one day apart.
    assert [task["plannedDay"] for task in found] == ["2026-11-19", "2026-11-20", "2026-11-21"]
    assert sessions(tasks_client, NEXT_WEEK) == []


def test_a_goal_made_on_saturday_has_two_sessions(
    tasks_client: TestClient, fixed_clock: FixedClock
) -> None:
    fixed_clock.instant = SATURDAY

    create_goal(tasks_client, lifting())

    assert len(sessions(tasks_client, WEEK)) == 2


def test_a_goal_made_on_sunday_evening_gets_next_weeks_full_target(
    tasks_client: TestClient, fixed_clock: FixedClock
) -> None:
    fixed_clock.instant = SUNDAY_EVENING

    create_goal(tasks_client, lifting())

    assert len(sessions(tasks_client, WEEK)) == 0  # its target starts next week
    assert len(sessions(tasks_client, NEXT_WEEK)) == 3


def test_raising_the_target_adds_a_session(tasks_client: TestClient) -> None:
    goal = create_goal(tasks_client, lifting())

    set_target(tasks_client, goal["id"], 4)

    assert len(sessions(tasks_client, WEEK)) == 4


def test_lowering_the_target_removes_the_last_open_session_bank_first(
    tasks_client: TestClient,
) -> None:
    goal = create_goal(tasks_client, lifting())
    first, second, third = sessions(tasks_client, WEEK)
    place(tasks_client, first["id"], date(2026, 11, 19))
    place(tasks_client, second["id"], date(2026, 11, 21))

    set_target(tasks_client, goal["id"], 2)

    left = sessions(tasks_client, WEEK)
    assert {task["id"] for task in left} == {first["id"], second["id"]}  # the bank one went

    set_target(tasks_client, goal["id"], 1)

    assert [task["id"] for task in sessions(tasks_client, WEEK)] == [first["id"]]  # latest day


def test_lowering_never_removes_a_done_or_set_aside_session(tasks_client: TestClient) -> None:
    goal = create_goal(tasks_client, lifting())
    done, *_ = sessions(tasks_client, WEEK)
    check_off(tasks_client, done["id"])

    set_target(tasks_client, goal["id"], 1)

    assert [task["id"] for task in sessions(tasks_client, WEEK)] == [done["id"]]


def test_a_removed_session_is_not_made_again(tasks_client: TestClient) -> None:
    goal = create_goal(tasks_client, lifting())
    set_target(tasks_client, goal["id"], 2)

    set_target(tasks_client, goal["id"], 3)  # the third number is deleted, so it isn't remade

    assert len(sessions(tasks_client, WEEK)) == 2


def test_a_target_changed_on_sunday_evening_leaves_this_week_as_it_was(
    tasks_client: TestClient, fixed_clock: FixedClock
) -> None:
    goal = create_goal(tasks_client, lifting())  # Wednesday: three sessions this week
    fixed_clock.instant = SUNDAY_EVENING
    tasks_client.get(f"/api/weeks/{NEXT_WEEK}")  # opens next week

    set_target(tasks_client, goal["id"], 2)

    assert len(sessions(tasks_client, WEEK)) == 3
    assert len(sessions(tasks_client, NEXT_WEEK)) == 2


def test_a_goal_paused_in_one_week_and_resumed_in_a_later_one_gets_that_weeks_sessions(
    tasks_client: TestClient, fixed_clock: FixedClock, connection: Connection
) -> None:
    goal = create_goal(tasks_client, lifting())
    tasks_client.post(f"/api/goals/{goal['id']}/pause")

    fixed_clock.instant = datetime(2026, 11, 25, 19, 0, tzinfo=UTC)  # Wednesday the 25th
    tasks_client.post(f"/api/goals/{goal['id']}/resume")

    assert len(sessions(tasks_client, NEXT_WEEK)) == 3
    old = connection.execute(
        text("select state from tasks where period_start = :week"), {"week": WEEK}
    ).all()
    assert {row.state for row in old} == {"lapsed"}
    assert not connection.execute(
        text(
            "select 1 from task_weeks where week = :week and outcome in ('lapsed', 'rolled_over')"
        ),
        {"week": WEEK},
    ).all()
