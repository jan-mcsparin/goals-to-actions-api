"""The next 12 weeks in one read (spec `coming-up`)."""

from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests.conftest import FixedClock
from tests.test_any_week import at, get_week
from tests.test_check_off import check_off
from tests.test_goals import ZONE, create_goal, lifting
from tests.test_recurring_items import BATHROOM, item
from tests.test_recurring_items import create as create_item
from tests.test_tasks import add_task, one_off

NEXT_WEEK = date(2026, 11, 23)
SUNDAY_EVENING = at(date(2026, 11, 22), 19)


def week(n: int) -> date:
    """Coming up's nth week, from 1."""
    return NEXT_WEEK + timedelta(weeks=n - 1)


@pytest.fixture
def tasks_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


def coming_up(client: TestClient) -> Any:
    response = client.get("/api/coming-up")
    assert response.status_code == 200, response.text
    return response.json()["weeks"]


def listed(client: TestClient) -> dict[str, list[str]]:
    """Each week's dated tasks by title, for the weeks that have any."""
    return {
        shown["week"]: [task["title"] for task in shown["tasks"]]
        for shown in coming_up(client)
        if shown["tasks"]
    }


def bank_task_due(client: TestClient, title: str, due: date) -> Any:
    """A task in this week's bank, given a due date later."""
    banked = add_task(client, title=title)
    edited = client.patch(f"/api/tasks/{banked['id']}", json={"title": title, "dueDate": str(due)})
    assert edited.status_code == 200, edited.text
    return banked


# The weeks


def test_twelve_weeks_from_next_week(tasks_client: TestClient) -> None:
    weeks = coming_up(tasks_client)

    assert [shown["week"] for shown in weeks] == [str(week(n)) for n in range(1, 13)]
    assert {shown["status"] for shown in weeks} == {"notOpen"}


def test_on_sunday_evening_the_first_week_is_open(
    tasks_client: TestClient, fixed_clock: FixedClock
) -> None:
    fixed_clock.instant = SUNDAY_EVENING

    weeks = coming_up(tasks_client)

    assert [shown["status"] for shown in weeks[:2]] == ["open", "notOpen"]


def test_after_a_wrap_up_the_weeks_start_a_week_later(
    tasks_client: TestClient, fixed_clock: FixedClock
) -> None:
    fixed_clock.instant = SUNDAY_EVENING
    wrapped = tasks_client.post("/api/weeks/2026-11-16/wrap-up")
    assert wrapped.status_code == 200, wrapped.text

    weeks = coming_up(tasks_client)

    assert [weeks[0]["week"], weeks[-1]["week"]] == [str(week(2)), str(week(13))]


# Counts


def a_busy_quarter(client: TestClient) -> Any:
    """Two goals with targets, one starting in week 3; a paused goal with a task due; a weekly,
    a monthly and a two-week item; tasks pinned, due and banked in later weeks."""
    goal = create_goal(client, lifting())
    create_goal(client, lifting(label="Swim", startDate="2026-12-09"))
    rest = create_goal(client, lifting(label="Rest"))
    add_task(client, title="Resting", goalId=rest["id"], dueDate="2026-12-10")
    assert client.post(f"/api/goals/{rest['id']}/pause").status_code == 200
    create_item(client, item())
    create_item(client, item(name="Pay rent", schedule={"kind": "monthly", "dayOfMonth": 10}))
    create_item(client, item(**BATHROOM))
    add_task(client, title="Pinned", day="2026-12-23")
    add_task(client, title="Due", dueDate="2026-12-10")
    bank_task_due(client, "Banked", date(2026, 12, 2))
    return goal


def assert_counts_agree_with_the_week_read(client: TestClient) -> None:
    for shown in coming_up(client):
        assert shown["counts"] == get_week(client, date.fromisoformat(shown["week"]))["counts"]


def test_each_weeks_counts_are_the_week_reads(tasks_client: TestClient) -> None:
    a_busy_quarter(tasks_client)

    assert_counts_agree_with_the_week_read(tasks_client)


def test_counts_agree_once_next_week_is_open_and_its_target_changed(
    tasks_client: TestClient, fixed_clock: FixedClock
) -> None:
    goal = a_busy_quarter(tasks_client)
    fixed_clock.instant = SUNDAY_EVENING
    target = {"kind": "count", "sessions": 5, "unit": "lifting sessions"}
    changed = tasks_client.put(f"/api/goals/{goal['id']}/weekly-target", json=target)
    assert changed.status_code == 200, changed.text

    weeks = coming_up(tasks_client)

    assert weeks[0]["status"] == "open"
    assert weeks[1]["counts"]["goalSessions"] == 5  # Swim starts in week 3
    assert_counts_agree_with_the_week_read(tasks_client)


# What's listed


def test_dated_tasks_are_listed_in_the_week_of_their_day(tasks_client: TestClient) -> None:
    add_task(tasks_client, title="Five weeks out", day="2026-12-23")
    add_task(tasks_client, title="Due in week 3", dueDate="2026-12-09")
    bank_task_due(tasks_client, "In this week's bank", date(2026, 12, 2))
    move = one_off(tasks_client)
    add_task(tasks_client, title="Pack the books", goalId=move["id"], dueDate="2026-12-16")
    add_task(tasks_client, title="Week 12", dueDate="2027-02-14")

    assert listed(tasks_client) == {
        str(week(2)): ["In this week's bank"],
        str(week(3)): ["Due in week 3"],
        str(week(4)): ["Pack the books"],
        str(week(5)): ["Five weeks out"],
        str(week(12)): ["Week 12"],
    }


def test_a_weeks_tasks_are_by_day_then_time(tasks_client: TestClient) -> None:
    add_task(tasks_client, title="Wednesday", dueDate="2026-12-09")
    add_task(
        tasks_client,
        title="Tuesday at 9",
        day="2026-12-08",
        timeOfDay={"kind": "at", "time": "09:00"},
    )
    add_task(
        tasks_client,
        title="Tuesday at 8",
        day="2026-12-08",
        timeOfDay={"kind": "at", "time": "08:00"},
    )

    assert listed(tasks_client) == {str(week(3)): ["Tuesday at 8", "Tuesday at 9", "Wednesday"]}


def test_a_task_set_to_a_day_is_listed_once_on_its_day(tasks_client: TestClient) -> None:
    add_task(tasks_client, title="Set to week 1", day="2026-11-25", dueDate="2026-12-16")
    add_task(tasks_client, title="Set to this week", day="2026-11-20", dueDate="2026-12-09")

    assert listed(tasks_client) == {str(week(1)): ["Set to week 1"]}


def test_whats_not_dated_in_the_twelve_weeks_or_not_open_isnt_listed(
    tasks_client: TestClient,
) -> None:
    done = bank_task_due(tasks_client, "Done", date(2026, 12, 2))
    check_off(tasks_client, done["id"])
    dropped = bank_task_due(tasks_client, "Dropped", date(2026, 12, 2))
    assert tasks_client.post(f"/api/tasks/{dropped['id']}/drop").is_success
    paused = create_goal(tasks_client, lifting())
    add_task(tasks_client, title="Paused goal's", goalId=paused["id"], dueDate="2026-12-09")
    assert tasks_client.post(f"/api/goals/{paused['id']}/pause").is_success
    add_task(tasks_client, title="Due this week", dueDate="2026-11-20")
    add_task(tasks_client, title="Week 13", dueDate="2027-02-15")

    assert listed(tasks_client) == {}


def test_recurring_work_isnt_listed(tasks_client: TestClient, fixed_clock: FixedClock) -> None:
    create_item(tasks_client, item())
    create_goal(tasks_client, lifting())
    fixed_clock.instant = SUNDAY_EVENING

    weeks = coming_up(tasks_client)

    assert weeks[0]["status"] == "open"
    assert get_week(tasks_client, week(1))["tasks"], "next week has its recurring work"
    assert listed(tasks_client) == {}


def test_check_ins_and_deadlines_are_listed_in_their_week(tasks_client: TestClient) -> None:
    goal = create_goal(tasks_client, lifting(deadline="2026-12-10"))
    milestone_id = str(uuid4())
    milestone = {"goalId": goal["id"], "measurableLine": "Bench", "targetDate": "2026-12-09"}
    assert tasks_client.put(f"/api/milestones/{milestone_id}", json=milestone).is_success

    weeks = {shown["week"]: shown for shown in coming_up(tasks_client)}

    third = weeks[str(week(3))]
    assert [c["milestoneId"] for c in third["checkIns"]] == [milestone_id]
    assert third["deadlines"] == [
        {"goalId": goal["id"], "goalLabel": goal["label"], "day": "2026-12-10"}
    ]
    assert [w for w, shown in weeks.items() if shown["checkIns"] or shown["deadlines"]] == [
        str(week(3))
    ]
