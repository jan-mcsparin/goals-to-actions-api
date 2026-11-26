"""Reading any week, past or later, with how full it is (spec `any-week`)."""

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from tests.conftest import FixedClock
from tests.test_check_off import check_off
from tests.test_goals import ZONE, create_goal, lifting
from tests.test_recurring_items import BATHROOM, LAUNDRY, item
from tests.test_recurring_items import create as create_item
from tests.test_tasks import add_task, one_off, open_next_week

THIS_WEEK = date(2026, 11, 16)
LAST_WEEK = THIS_WEEK - timedelta(weeks=1)
NEXT_WEEK = THIS_WEEK + timedelta(weeks=1)
LATER = THIS_WEEK + timedelta(weeks=3)


@pytest.fixture
def tasks_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


def at(day: date, hour: int = 12) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=ZoneInfo(ZONE))


def get_week(client: TestClient, week: date) -> Any:
    response = client.get(f"/api/weeks/{week.isoformat()}")
    assert response.status_code == 200, response.text
    return response.json()


def by_title(week: Any) -> dict[str, Any]:
    return {task["title"]: task for task in week["tasks"]}


def set_row_outcome(connection: Connection, task_id: str, outcome: str) -> None:
    connection.execute(
        text("update task_weeks set outcome = :outcome where task_id = :id"),
        {"outcome": outcome, "id": task_id},
    )


# Status, and what a closed week lists


def a_week_that_closed(client: TestClient, clock: FixedClock) -> dict[str, Any]:
    """This week with a goal's three sessions (one done), a task done and one left open;
    then the clock moves on a week, so the sessions left lapse and the open task rolls over."""
    goal = create_goal(client, lifting())
    done = add_task(client, title="Done", day="2026-11-18")
    check_off(client, done["id"])
    rolls = add_task(client, title="Rolls", day="2026-11-19")
    sessions = [t for t in get_week(client, THIS_WEEK)["tasks"] if t["origin"] == "weeklyTarget"]
    check_off(client, sessions[0]["id"])
    clock.instant = at(date(2026, 11, 25))
    return {"goal": goal, "done": done, "rolls": rolls}


def test_a_closed_week_lists_what_was_on_it_and_how_each_ended(
    tasks_client: TestClient, fixed_clock: FixedClock
) -> None:
    made = a_week_that_closed(tasks_client, fixed_clock)

    week = get_week(tasks_client, THIS_WEEK)

    assert week["status"] == "closed"
    shown = by_title(week)
    assert (shown["Done"]["state"], shown["Done"]["weekOutcome"]) == ("done", None)
    assert (shown["Rolls"]["state"], shown["Rolls"]["weekOutcome"]) == ("open", "rolledOver")
    assert shown["Rolls"]["plannedDay"] == "2026-11-19"
    assert shown["Rolls"]["atClose"] is None
    sessions = [t for t in week["tasks"] if t["origin"] == "weeklyTarget"]
    assert sorted((t["state"], t["weekOutcome"]) for t in sessions) == [
        ("done", None),
        ("lapsed", "lapsed"),
        ("lapsed", "lapsed"),
    ]
    # The task that rolled over is in play in the new week, with no outcome.
    [moved] = [t for t in get_week(tasks_client, NEXT_WEEK)["tasks"] if t["title"] == "Rolls"]
    assert (moved["weekOutcome"], moved["carriedOver"]) == (None, 1)
    assert made["goal"]["id"] in [goal["id"] for goal in week["goals"]]


def test_a_closed_weeks_progress_keeps_a_goal_ended_since(
    tasks_client: TestClient, fixed_clock: FixedClock
) -> None:
    made = a_week_that_closed(tasks_client, fixed_clock)
    ended = tasks_client.post(f"/api/goals/{made['goal']['id']}/end")
    assert ended.status_code == 200, ended.text

    [goal] = get_week(tasks_client, THIS_WEEK)["goals"]

    assert (goal["id"], goal["progress"]) == (made["goal"]["id"], {"done": 1, "of": 3})


def test_a_goal_paused_before_its_week_opened_is_not_in_that_weeks_progress(
    tasks_client: TestClient, fixed_clock: FixedClock
) -> None:
    goal = create_goal(tasks_client, lifting())
    fixed_clock.instant = at(date(2026, 11, 20))
    paused = tasks_client.post(f"/api/goals/{goal['id']}/pause")
    assert paused.status_code == 200, paused.text
    fixed_clock.instant = at(date(2026, 11, 22), 19)
    assert get_week(tasks_client, NEXT_WEEK)["status"] == "open"  # opened, with no sessions
    fixed_clock.instant = at(date(2026, 12, 2))
    resumed = tasks_client.post(f"/api/goals/{goal['id']}/resume")
    assert resumed.status_code == 200, resumed.text

    assert get_week(tasks_client, NEXT_WEEK)["goals"] == []


def test_set_aside_and_dropped_rows_stay_out_of_a_closed_week(
    tasks_client: TestClient, fixed_clock: FixedClock, connection: Connection
) -> None:
    aside = add_task(tasks_client, title="Aside")
    dropped = add_task(tasks_client, title="Dropped")
    set_row_outcome(connection, aside["id"], "set_aside")
    set_row_outcome(connection, dropped["id"], "dropped")
    fixed_clock.instant = at(date(2026, 11, 25))

    assert get_week(tasks_client, THIS_WEEK)["tasks"] == []


def test_each_week_has_its_status(
    tasks_client: TestClient, fixed_clock: FixedClock, connection: Connection
) -> None:
    def status(week: date) -> str:
        return str(get_week(tasks_client, week)["status"])

    assert [status(w) for w in (LAST_WEEK, THIS_WEEK, NEXT_WEEK, LATER)] == [
        "closed",
        "open",
        "notOpen",
        "notOpen",
    ]
    open_next_week(connection)
    assert [status(w) for w in (THIS_WEEK, NEXT_WEEK, LATER)] == ["open", "open", "notOpen"]


def test_a_week_nobody_opened_reads_closed_and_empty(
    tasks_client: TestClient, fixed_clock: FixedClock
) -> None:
    add_task(tasks_client, title="Waits")
    fixed_clock.instant = at(date(2026, 12, 9))  # 23 Nov and 30 Nov never opened

    week = get_week(tasks_client, NEXT_WEEK)

    assert (week["status"], week["tasks"], week["goals"]) == ("closed", [], [])


def test_a_week_that_has_not_opened_shows_its_pinned_rows_and_no_goals(
    tasks_client: TestClient,
) -> None:
    create_goal(tasks_client, lifting())
    add_task(tasks_client, title="Pinned", day=(LATER + timedelta(days=2)).isoformat())

    week = get_week(tasks_client, LATER)

    assert [task["title"] for task in week["tasks"]] == ["Pinned"]
    assert week["goals"] == []


# How far back


def test_first_week_is_empty_with_no_rows(tasks_client: TestClient) -> None:
    assert get_week(tasks_client, THIS_WEEK)["firstWeek"] is None


def test_first_week_is_the_earliest_row_of_any_outcome(
    tasks_client: TestClient, connection: Connection
) -> None:
    add_task(tasks_client, title="Later", day=(LATER + timedelta(days=1)).isoformat())
    assert get_week(tasks_client, LATER)["firstWeek"] == LATER.isoformat()

    early = add_task(tasks_client, title="Early")
    set_row_outcome(connection, early["id"], "set_aside")

    assert get_week(tasks_client, LATER)["firstWeek"] == THIS_WEEK.isoformat()
    assert get_week(tasks_client, LAST_WEEK)["firstWeek"] == THIS_WEEK.isoformat()


# Actual counts: every task the read returns, by origin


def day_counts(week: Any) -> dict[str, Any]:
    return {day["day"]: day["counts"] for day in week["days"]}


def zero(**counts: int) -> dict[str, int]:
    return {"goalSessions": 0, "upkeep": 0, "added": 0} | counts


def test_an_open_week_counts_its_tasks_by_origin(tasks_client: TestClient) -> None:
    create_goal(tasks_client, lifting())
    run = {"kind": "amount", "sessions": 2, "amount": 10, "unit": "km"}
    create_goal(tasks_client, lifting(label="Run", weeklyTarget=run))
    create_item(tasks_client, item(**LAUNDRY))
    step_goal = one_off(tasks_client)
    add_task(tasks_client, title="Step", goalId=step_goal["id"], day="2026-11-20")
    add_task(tasks_client, title="Today", day="2026-11-18")

    week = get_week(tasks_client, THIS_WEEK)

    assert week["counts"] == {"goalSessions": 5, "goals": 2, "upkeep": 1, "added": 2}
    by_day = day_counts(week)
    assert by_day["2026-11-18"]["added"] == 1
    on_days = [task for task in week["tasks"] if task["plannedDay"]]
    assert sum(sum(counts.values()) for counts in by_day.values()) == len(on_days)


def test_a_closed_week_counts_what_rolled_over_and_lapsed(
    tasks_client: TestClient, fixed_clock: FixedClock
) -> None:
    a_week_that_closed(tasks_client, fixed_clock)

    week = get_week(tasks_client, THIS_WEEK)

    assert week["counts"] == {"goalSessions": 3, "goals": 1, "upkeep": 0, "added": 2}
    assert day_counts(week)["2026-11-19"]["added"] == 1
    # The task that rolled over counts in its new week too.
    assert get_week(tasks_client, NEXT_WEEK)["counts"]["added"] == 1


def test_a_skipped_week_counts_nothing(tasks_client: TestClient, fixed_clock: FixedClock) -> None:
    create_item(tasks_client, item(**LAUNDRY))
    fixed_clock.instant = at(date(2026, 12, 9))

    week = get_week(tasks_client, NEXT_WEEK)

    assert week["counts"] == {"goalSessions": 0, "goals": 0, "upkeep": 0, "added": 0}
    assert all(counts == zero() for counts in day_counts(week).values())


def test_a_week_that_has_not_opened_has_no_day_counts(tasks_client: TestClient) -> None:
    add_task(tasks_client, title="Pinned", day=(LATER + timedelta(days=2)).isoformat())

    assert all(counts is None for counts in day_counts(get_week(tasks_client, LATER)).values())


# Expected counts: what opening a later week would bring


def a_later_week(client: TestClient) -> None:
    """Three weeks out (7 Dec): two goals with targets, one starting that Saturday; a paused
    goal; a weekly, a monthly and a two-week item (in the second week of its period); a task
    pinned there, a task due there with no row, and one in this week's bank due there."""
    create_goal(client, lifting())
    create_goal(client, lifting(label="Swim", startDate="2026-12-12"))
    rest = create_goal(client, lifting(label="Rest"))
    assert client.post(f"/api/goals/{rest['id']}/pause").status_code == 200
    create_item(client, item())
    create_item(client, item(name="Pay rent", schedule={"kind": "monthly", "dayOfMonth": 10}))
    create_item(client, item(**BATHROOM))
    add_task(client, title="Pinned", day="2026-12-09")
    add_task(client, title="Due", dueDate="2026-12-10")
    banked = add_task(client, title="Banked")
    edited = client.patch(
        f"/api/tasks/{banked['id']}", json={"title": "Banked", "dueDate": "2026-12-10"}
    )
    assert edited.status_code == 200, edited.text


EXPECTED = {"goalSessions": 5, "goals": 2, "upkeep": 2, "added": 2}


def test_a_week_that_has_not_opened_counts_what_opening_would_bring(
    tasks_client: TestClient,
) -> None:
    a_later_week(tasks_client)

    week = get_week(tasks_client, LATER)

    assert week["status"] == "notOpen"
    assert week["counts"] == EXPECTED
    assert [task["title"] for task in week["tasks"]] == ["Pinned"]


def test_once_opened_a_week_counts_what_was_expected(
    tasks_client: TestClient, fixed_clock: FixedClock
) -> None:
    a_later_week(tasks_client)
    for sunday in (date(2026, 11, 22), date(2026, 11, 29), date(2026, 12, 6)):
        fixed_clock.instant = at(sunday, 19)
        get_week(tasks_client, LATER)

    week = get_week(tasks_client, LATER)

    assert week["status"] == "open"
    assert week["counts"] == EXPECTED
