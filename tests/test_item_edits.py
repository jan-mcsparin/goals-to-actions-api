"""An edit to a recurring item renames its open tasks and moves this week's work to the new
schedule (spec `recurring-edit`)."""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from tests.conftest import FixedClock
from tests.test_check_off import check_off
from tests.test_goals import ZONE
from tests.test_recurring_items import create, item, turn
from tests.test_task_moves import place

WEEK = date(2026, 11, 16)
MON, TUE, WED, THU, FRI, SAT = (f"2026-11-{day}" for day in (16, 17, 18, 19, 20, 21))
LAST_WEDNESDAY = datetime(2026, 11, 11, 19, 0, tzinfo=UTC)
THIS_WEDNESDAY = datetime(2026, 11, 18, 19, 0, tzinfo=UTC)
STARTS = "2026-11-01"


@pytest.fixture
def items_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


def weekly(weekday: str, name: str = "Take out the trash") -> dict[str, Any]:
    return item(name=name, schedule={"kind": "weekly", "weekday": weekday}, startsOn=STARTS)


def edit(client: TestClient, created: dict[str, Any], **changes: Any) -> Any:
    body = {
        "name": created["name"],
        "aspirationId": created["aspirationId"],
        "schedule": created["schedule"],
        "startsOn": created["startsOn"],
    } | changes
    response = client.patch(f"/api/recurring-items/{created['id']}", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def item_tasks(client: TestClient, week: date = WEEK) -> list[Any]:
    tasks = client.get(f"/api/weeks/{week}").json()["tasks"]
    return [task for task in tasks if task["origin"] == "recurringItem"]


def days(client: TestClient) -> list[Any]:
    return [task["plannedDay"] for task in item_tasks(client)]


def set_day(connection: Connection, task_id: str, day: str | None) -> None:
    connection.execute(
        text("update task_weeks set planned_day = :day where task_id = :id and week = :week"),
        {"day": day, "id": task_id, "week": WEEK},
    )


def titles_by_state(connection: Connection, item_id: str) -> dict[str, set[str]]:
    rows = connection.execute(
        text("select state, title from tasks where recurring_item_id = :id"), {"id": item_id}
    )
    found: dict[str, set[str]] = {}
    for state, title in rows:
        found.setdefault(state, set()).add(title)
    return found


# A rename


def test_a_rename_renames_open_tasks_and_keeps_done_ones(
    items_client: TestClient, connection: Connection
) -> None:
    created = create(
        items_client,
        item(name="Stretch", schedule={"kind": "flexible", "times": 3, "period": "week"}),
    )
    first, second, _ = item_tasks(items_client)
    check_off(items_client, first["id"])
    items_client.post(f"/api/tasks/{second['id']}/drop")

    edit(items_client, created, name="Stretch and breathe")

    assert titles_by_state(connection, created["id"]) == {
        "done": {"Stretch"},
        "dropped": {"Stretch"},
        "open": {"Stretch and breathe"},
    }


def test_a_rename_reaches_a_set_aside_task(
    items_client: TestClient, connection: Connection
) -> None:
    created = create(items_client, weekly("thursday"))
    turn(items_client, created["id"], "off")

    edit(items_client, created, name="Trash and recycling")

    assert titles_by_state(connection, created["id"]) == {"open": {"Trash and recycling"}}


def test_a_rename_alone_moves_nothing(items_client: TestClient, connection: Connection) -> None:
    created = create(items_client, weekly("thursday"))
    set_day(connection, item_tasks(items_client)[0]["id"], MON)

    edit(items_client, created, name="Trash and recycling")

    assert days(items_client) == [MON]


# A new day


def test_thursday_to_friday_moves_the_task(items_client: TestClient) -> None:
    created = create(items_client, weekly("thursday"))

    edit(items_client, created, schedule={"kind": "weekly", "weekday": "friday"})

    assert days(items_client) == [FRI]


def test_thursday_to_monday_leaves_it_on_thursday(items_client: TestClient) -> None:
    created = create(items_client, weekly("thursday"))

    edit(items_client, created, schedule={"kind": "weekly", "weekday": "monday"})

    assert days(items_client) == [THU]


def test_monday_not_done_to_friday_moves_it(
    items_client: TestClient, connection: Connection
) -> None:
    created = create(items_client, weekly("monday"))
    set_day(connection, item_tasks(items_client)[0]["id"], MON)

    edit(items_client, created, schedule={"kind": "weekly", "weekday": "friday"})

    assert days(items_client) == [FRI]


def test_monday_to_tuesday_leaves_it_on_monday(
    items_client: TestClient, connection: Connection
) -> None:
    created = create(items_client, weekly("monday"))
    set_day(connection, item_tasks(items_client)[0]["id"], MON)

    edit(items_client, created, schedule={"kind": "weekly", "weekday": "tuesday"})

    assert days(items_client) == [MON]


def test_a_done_task_stays_done_on_its_day(items_client: TestClient) -> None:
    created = create(items_client, weekly("wednesday"))
    check_off(items_client, item_tasks(items_client)[0]["id"])

    edit(items_client, created, schedule={"kind": "weekly", "weekday": "friday"})

    [task] = item_tasks(items_client)
    assert (task["plannedDay"], task["state"]) == (WED, "done")


def test_a_task_placed_by_hand_stays(items_client: TestClient, connection: Connection) -> None:
    created = create(items_client, weekly("thursday"))
    task_id = item_tasks(items_client)[0]["id"]
    set_day(connection, task_id, None)
    assert place(items_client, task_id, date(2026, 11, 21)).status_code == 200

    edit(items_client, created, schedule={"kind": "weekly", "weekday": "friday"})

    assert days(items_client) == [SAT]


def test_a_task_in_the_bank_goes_on_its_new_day(
    items_client: TestClient, connection: Connection
) -> None:
    created = create(items_client, weekly("thursday"))
    set_day(connection, item_tasks(items_client)[0]["id"], None)

    edit(items_client, created, schedule={"kind": "weekly", "weekday": "friday"})

    assert days(items_client) == [FRI]


def test_thursday_to_today_puts_it_on_today(items_client: TestClient) -> None:
    created = create(items_client, weekly("thursday"))

    edit(items_client, created, schedule={"kind": "weekly", "weekday": "wednesday"})

    assert days(items_client) == [WED]


def test_a_carry_over_from_last_week_stays_in_the_bank(
    items_client: TestClient, fixed_clock: FixedClock
) -> None:
    fixed_clock.instant = LAST_WEDNESDAY
    created = create(items_client, weekly("thursday"))
    fixed_clock.instant = THIS_WEDNESDAY
    assert sorted(days(items_client), key=str) == [THU, None]  # this week's, and the carry-over

    edit(items_client, created, schedule={"kind": "weekly", "weekday": "friday"})

    assert sorted(days(items_client), key=str) == [FRI, None]


# Counts, and a change of kind or period


def flexible(times: int, period: str = "week") -> dict[str, Any]:
    return {"kind": "flexible", "times": times, "period": period}


def stretch(times: int) -> dict[str, Any]:
    return item(name="Stretch", schedule=flexible(times), startsOn=STARTS)


def live_count(connection: Connection, item_id: str) -> int:
    return int(
        connection.execute(
            text("select count(*) from tasks where recurring_item_id = :id and deleted_at is null"),
            {"id": item_id},
        ).scalar_one()
    )


def test_raising_a_flexible_count_adds_one_after_today(items_client: TestClient) -> None:
    created = create(items_client, stretch(2))
    before = days(items_client)

    edit(items_client, created, schedule=flexible(3))

    after = days(items_client)
    assert len(after) == 3
    [added] = [day for day in after if day not in before] or [None]
    assert added is not None and added > WED


def test_lowering_a_flexible_count_removes_the_bank_first_then_the_latest_day(
    items_client: TestClient, connection: Connection
) -> None:
    created = create(items_client, stretch(3))
    first, second, third = item_tasks(items_client)
    check_off(items_client, first["id"])
    set_day(connection, second["id"], None)
    set_day(connection, third["id"], SAT)

    edit(items_client, created, schedule=flexible(1))

    [left] = item_tasks(items_client)
    assert (left["id"], left["state"]) == (first["id"], "done")


def test_lowering_never_removes_tasks_placed_by_hand(
    items_client: TestClient, connection: Connection
) -> None:
    created = create(items_client, stretch(3))
    tasks = item_tasks(items_client)
    for task, day in zip(tasks[:2], (date(2026, 11, 20), date(2026, 11, 21)), strict=True):
        set_day(connection, task["id"], None)
        assert place(items_client, task["id"], day).status_code == 200

    edit(items_client, created, schedule=flexible(1))

    assert sorted(days(items_client)) == [FRI, SAT]


def test_a_monthly_day_later_this_week_moves_the_task(items_client: TestClient) -> None:
    created = create(
        items_client,
        item(name="Pay rent", schedule={"kind": "monthly", "dayOfMonth": 19}, startsOn=STARTS),
    )

    edit(items_client, created, schedule={"kind": "monthly", "dayOfMonth": 20})

    assert days(items_client) == [FRI]


def test_a_monthly_day_outside_this_week_removes_the_open_task(
    items_client: TestClient, connection: Connection
) -> None:
    created = create(
        items_client,
        item(name="Pay rent", schedule={"kind": "monthly", "dayOfMonth": 19}, startsOn=STARTS),
    )

    edit(items_client, created, schedule={"kind": "monthly", "dayOfMonth": 1})

    assert item_tasks(items_client) == []
    assert live_count(connection, created["id"]) == 0


def test_weekly_done_to_three_a_week_adds_two_after_today(items_client: TestClient) -> None:
    created = create(items_client, weekly("wednesday", "Stretch"))
    check_off(items_client, item_tasks(items_client)[0]["id"])

    edit(items_client, created, schedule=flexible(3))

    tasks = item_tasks(items_client)
    assert [task["state"] for task in tasks].count("done") == 1
    assert all(task["plannedDay"] > WED for task in tasks if task["state"] == "open")
    assert len(tasks) == 3


def test_weekly_to_once_a_month_keeps_the_task_as_the_months(
    items_client: TestClient, fixed_clock: FixedClock, connection: Connection
) -> None:
    created = create(items_client, weekly("thursday"))
    [before] = item_tasks(items_client)

    edit(items_client, created, schedule=flexible(1, "month"))

    [after] = item_tasks(items_client)
    assert (after["id"], after["plannedDay"]) == (before["id"], THU)
    fixed_clock.instant = datetime(2026, 11, 23, 2, 0, tzinfo=UTC)  # Sunday evening
    items_client.get("/api/weeks/2026-11-23")  # opens next week, still November
    assert live_count(connection, created["id"]) == 1


def test_editing_back_and_forth_keeps_one_task(
    items_client: TestClient, connection: Connection
) -> None:
    created = create(items_client, stretch(3))

    for times in (1, 3, 2, 1, 3):
        edit(items_client, created, schedule=flexible(times))
        assert len(item_tasks(items_client)) == times

    assert live_count(connection, created["id"]) == 3
