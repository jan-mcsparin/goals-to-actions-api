"""The planner through the database and the API (spec `planner`): recurring work goes on days
when a week opens and as it arrives; everything else stays in the bank."""

from collections.abc import Iterator
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.config import FIXED_USER_ID
from app.db import planner
from app.planner import place_new_work
from app.turnover.rules import catch_up
from tests.conftest import FixedClock
from tests.test_goal_sessions import set_target
from tests.test_goals import ZONE, create_goal, lifting
from tests.test_open_week import NEXT_WEEK, WEEK, at, reset_markers
from tests.test_recurring_items import create as create_item
from tests.test_recurring_items import item, turn


def days(connection: Connection, week: date) -> dict[str, list[date | None]]:
    """Each title's days in `week`, by session number; `None` is the bank."""
    found: dict[str, list[date | None]] = {}
    for row in connection.execute(
        text(
            "select tasks.title, task_weeks.planned_day from task_weeks"
            " join tasks on tasks.id = task_weeks.task_id"
            " where task_weeks.week = :week and task_weeks.deleted_at is null"
            " and tasks.deleted_at is null order by tasks.title, tasks.number"
        ),
        {"week": week},
    ):
        found.setdefault(row.title, []).append(row.planned_day)
    return found


def d(day: int) -> date:
    return date(2026, 11, day)


@pytest.fixture
def planner_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


@pytest.fixture
def work(planner_client: TestClient, connection: Connection) -> Connection:
    """Trash on Tuesdays, Stretch twice a week (maintenance) and a lifting goal (3 a week),
    all started long ago, then every task cleared so the week is open to be opened."""
    create_goal(planner_client, lifting())
    create_item(planner_client, item(startsOn="2026-11-01"))
    create_item(
        planner_client,
        item(
            name="Stretch",
            schedule={"kind": "flexible", "times": 2, "period": "week"},
            startsOn="2026-11-01",
        ),
    )
    connection.execute(text("update goals set start_date = '2026-11-01'"))
    connection.execute(text("delete from task_weeks"))
    connection.execute(text("delete from tasks"))
    reset_markers(connection)
    return connection


def add_by_hand(connection: Connection, title: str, week: date | None = None) -> UUID:
    task_id = uuid4()
    connection.execute(
        text(
            "insert into tasks (id, user_id, title, origin, due_date)"
            " values (:id, :user_id, :title, 'by_hand', :due)"
        ),
        {"id": task_id, "user_id": FIXED_USER_ID, "title": title, "due": d(25)},
    )
    if week is not None:
        connection.execute(
            text(
                "insert into task_weeks (id, user_id, task_id, week)"
                " values (gen_random_uuid(), :user_id, :task_id, :week)"
            ),
            {"user_id": FIXED_USER_ID, "task_id": task_id, "week": week},
        )
    return task_id


def test_sunday_evening_places_next_weeks_recurring_work(work: Connection) -> None:
    catch_up(work, FIXED_USER_ID, at(d(22), 19))

    # Trash first, on its day; then Stretch (maintenance) three apart from Monday; then the
    # goal two apart, from the start whose days are lightest.
    assert days(work, NEXT_WEEK) == {
        "Take out the trash": [d(24)],
        "Stretch": [d(23), d(26)],
        "Be strong": [d(25), d(27), d(29)],
    }


def test_a_first_request_on_wednesday_places_from_wednesday(work: Connection) -> None:
    catch_up(work, FIXED_USER_ID, at(d(18), 12))

    assert days(work, WEEK) == {
        # Tuesday has passed, so the trash goes on the first day it may use.
        "Take out the trash": [d(18)],
        "Stretch": [d(19), d(21)],
        "Be strong": [d(20), d(21), d(22)],
    }


def test_work_under_an_aspiration_comes_before_goals_without_one(
    work: Connection, planner_client: TestClient
) -> None:
    aspiration = str(uuid4())
    response = planner_client.put(
        f"/api/aspirations/{aspiration}", json={"name": "Health", "why": "To keep going"}
    )
    assert response.status_code == 200, response.text
    create_goal(planner_client, lifting(label="Run", aspirationId=aspiration))
    work.execute(text("update goals set start_date = '2026-11-01'"))
    work.execute(text("delete from task_weeks"))
    work.execute(text("delete from tasks"))
    reset_markers(work)

    catch_up(work, FIXED_USER_ID, at(d(22), 19))

    placed = days(work, NEXT_WEEK)
    assert placed["Run"] == [d(25), d(27), d(29)]
    assert placed["Be strong"] == [d(24), d(26), d(28)]


def test_carry_overs_and_tasks_now_due_stay_in_the_bank(work: Connection) -> None:
    add_by_hand(work, "Call the bank", WEEK)
    add_by_hand(work, "Renew passport")
    catch_up(work, FIXED_USER_ID, at(d(18), 12))

    catch_up(work, FIXED_USER_ID, at(d(23), 9))

    placed = days(work, NEXT_WEEK)
    assert placed["Call the bank"] == [None]
    assert placed["Renew passport"] == [None]
    assert all(day is not None for day in placed["Be strong"])


def test_opening_twice_places_nothing_more(work: Connection) -> None:
    catch_up(work, FIXED_USER_ID, at(d(22), 19))
    before = days(work, NEXT_WEEK)

    reset_markers(work)
    catch_up(work, FIXED_USER_ID, at(d(22), 19))

    assert days(work, NEXT_WEEK) == before


def place(connection: Connection, task_id: UUID, day: date, first_day: date) -> int:
    return planner.Querier(connection).place_generated_task(
        planner.PlaceGeneratedTaskParams(
            day=day, task_id=task_id, user_id=FIXED_USER_ID, week=WEEK, first_day=first_day
        )
    )


def test_the_write_refuses_a_day_before_the_first_day(work: Connection) -> None:
    task_id = add_by_hand(work, "Any", WEEK)

    assert place(work, task_id, d(18), d(19)) == 0
    assert place(work, task_id, d(19), d(19)) == 1


def test_the_write_refuses_a_row_already_on_a_day_or_placed_by_hand(work: Connection) -> None:
    task_id = add_by_hand(work, "Any", WEEK)
    work.execute(
        text("update task_weeks set planned_day = :day, placed_by_hand = true"),
        {"day": d(20)},
    )

    assert place(work, task_id, d(21), d(19)) == 0
    work.execute(text("update task_weeks set placed_by_hand = false"))
    assert place(work, task_id, d(21), d(19)) == 0
    assert days(work, WEEK) == {"Any": [d(20)]}


def test_the_write_refuses_a_settled_row(work: Connection) -> None:
    task_id = add_by_hand(work, "Any", WEEK)
    work.execute(text("update task_weeks set outcome = 'set_aside'"))

    assert place(work, task_id, d(21), d(19)) == 0


def test_a_task_added_by_hand_is_never_placed(work: Connection) -> None:
    task_id = add_by_hand(work, "Any", WEEK)
    work.execute(text("update users set planned_through_week = :week"), {"week": WEEK})

    place_new_work(work, FIXED_USER_ID, [task_id], d(19))

    assert days(work, WEEK) == {"Any": [None]}


def test_placing_is_audited_with_the_write_that_caused_it(
    work: Connection, planner_client: TestClient
) -> None:
    last = work.execute(text("select coalesce(max(id), 0) from audit_log")).scalar_one()
    assert planner_client.get(f"/api/weeks/{WEEK}").status_code == 200

    actions = {
        row.action
        for row in work.execute(
            text(
                "select action from audit_log where table_name = 'task_weeks'"
                " and operation = 'update' and old_row->>'planned_day' is null"
                " and new_row->>'planned_day' is not null and id > :last"
            ),
            {"last": last},
        )
    }
    assert actions == {"open week"}


# New recurring work mid-week. The week below is opened on the pinned Wednesday, 18 Nov:
# trash on Wed 18, Stretch on Thu 19 and Sat 21, Be strong on Fri 20, Sat 21 and Sun 22.


def week_tasks(client: TestClient) -> dict[str, dict[str, Any]]:
    response = client.get(f"/api/weeks/{WEEK}")
    assert response.status_code == 200, response.text
    return {task["id"]: task for task in response.json()["tasks"]}


def on_today(client: TestClient) -> list[dict[str, Any]]:
    return [task for task in week_tasks(client).values() if task["plannedDay"] == "2026-11-18"]


def by_title(client: TestClient, title: str) -> list[str | None]:
    found = [task for task in week_tasks(client).values() if task["title"] == title]
    return sorted(task["plannedDay"] or "bank" for task in found)


@pytest.fixture
def opened(work: Connection, planner_client: TestClient) -> TestClient:
    planner_client.get(f"/api/weeks/{WEEK}")
    return planner_client


def goal_id(connection: Connection) -> str:
    return str(connection.execute(text("select id from goals")).scalar_one())


def test_a_goal_made_midweek_goes_on_later_days(opened: TestClient) -> None:
    today = on_today(opened)

    create_goal(opened, lifting(label="Run"))

    assert by_title(opened, "Run") == ["2026-11-19", "2026-11-20", "2026-11-21"]
    assert on_today(opened) == today


def test_a_goal_made_on_sunday_leaves_its_session_in_the_bank(
    work: Connection, planner_client: TestClient, fixed_clock: FixedClock
) -> None:
    fixed_clock.instant = at(d(22), 15)

    create_goal(planner_client, lifting(label="Run"))

    assert by_title(planner_client, "Run") == ["bank"]


def test_a_raised_target_goes_on_the_lightest_later_day_without_a_session(
    opened: TestClient, work: Connection
) -> None:
    today = on_today(opened)

    set_target(opened, goal_id(work), 4)

    assert by_title(opened, "Be strong") == ["2026-11-19", "2026-11-20", "2026-11-21", "2026-11-22"]
    assert on_today(opened) == today


def test_a_new_flexible_item_spreads_over_later_days(opened: TestClient) -> None:
    today = on_today(opened)

    create_item(
        opened,
        item(name="Walk", schedule={"kind": "flexible", "times": 2, "period": "week"}),
    )

    assert by_title(opened, "Walk") == ["2026-11-20", "2026-11-22"]
    assert on_today(opened) == today


def test_an_item_turned_off_and_on_gets_its_tasks_back_and_nothing_new(
    opened: TestClient,
) -> None:
    before = week_tasks(opened)
    stretch = next(task for task in before.values() if task["title"] == "Stretch")

    turn(opened, stretch["recurringItemId"], "off")
    turn(opened, stretch["recurringItemId"], "on")

    after = week_tasks(opened)
    assert after.keys() == before.keys()
    assert on_today(opened) == [
        task for task in before.values() if task["plannedDay"] == "2026-11-18"
    ]


def test_a_goal_paused_and_resumed_places_nothing_new(opened: TestClient, work: Connection) -> None:
    today = on_today(opened)
    others = {i: t for i, t in week_tasks(opened).items() if t["title"] != "Be strong"}

    for action in ("pause", "resume"):
        response = opened.post(f"/api/goals/{goal_id(work)}/{action}")
        assert response.status_code == 200, response.text

    after = week_tasks(opened)
    assert {i: t for i, t in after.items() if t["title"] != "Be strong"} == others
    assert len(by_title(opened, "Be strong")) == 3
    assert on_today(opened) == today


def test_a_check_off_made_early_leaves_every_other_row_as_it_was(opened: TestClient) -> None:
    before = week_tasks(opened)
    session = next(task for task in before.values() if task["plannedDay"] == "2026-11-22")

    response = opened.post(
        f"/api/tasks/{session['id']}/check-off",
        json={"completedAt": "2026-11-18T19:30:00Z", "completedOn": "2026-11-18"},
    )
    assert response.status_code == 200, response.text

    after = week_tasks(opened)
    del before[session["id"]], after[session["id"]]
    assert after == before


def test_a_task_sent_to_the_bank_stays_there_and_nothing_fills_its_day(
    opened: TestClient,
) -> None:
    before = week_tasks(opened)
    session = next(task for task in before.values() if task["plannedDay"] == "2026-11-20")

    response = opened.post(f"/api/tasks/{session['id']}/bank", json={"week": str(WEEK)})
    assert response.status_code == 200, response.text

    after = week_tasks(opened)
    assert after[session["id"]]["plannedDay"] is None
    del before[session["id"]], after[session["id"]]
    assert after == before
