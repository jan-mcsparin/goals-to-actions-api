"""The planner through the database and the API (spec `planner`): recurring work goes on days
when a week opens and as it arrives; everything else stays in the bank."""

from collections.abc import Iterator
from datetime import date
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.config import FIXED_USER_ID
from app.db import planner
from app.planner import place_new_work
from app.turnover.rules import catch_up
from tests.test_goals import ZONE, create_goal, lifting
from tests.test_open_week import NEXT_WEEK, WEEK, at, reset_markers
from tests.test_recurring_items import create as create_item
from tests.test_recurring_items import item


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
