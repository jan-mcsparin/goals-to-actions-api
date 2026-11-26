from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.weeks import week_of
from tests.test_aspirations import add_other_user
from tests.test_aspirations import create as create_aspiration
from tests.test_check_off import check_off
from tests.test_goals import ZONE, create_goal, lifting, no_sugar, today
from tests.test_recurring_items import create as create_item
from tests.test_recurring_items import item
from tests.test_tasks import add_task, open_next_week


@pytest.fixture
def tasks_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


def this_week() -> str:
    return week_of(today()).isoformat()


def get_week(client: TestClient, week: str) -> Any:
    response = client.get(f"/api/weeks/{week}")
    assert response.status_code == 200, response.text
    return response.json()


def titles(week: Any) -> list[str]:
    """Titles of the tasks added by hand; a goal's own sessions are left out."""
    return [task["title"] for task in week["tasks"] if task["origin"] == "byHand"]


def test_the_week_lists_its_days_then_its_bank(tasks_client: TestClient) -> None:
    goal = create_goal(tasks_client, lifting())
    add_task(tasks_client, title="In the bank", goalId=goal["id"])
    add_task(
        tasks_client,
        title="At six",
        day=today().isoformat(),
        timeOfDay={"kind": "at", "time": "18:00"},
    )
    add_task(tasks_client, title="Today", day=today().isoformat())
    add_task(tasks_client, title="Waiting", dueDate=(today() + timedelta(days=8)).isoformat())

    week = get_week(tasks_client, this_week())

    assert (week["week"], week["isCurrent"], week["nextWeekOpen"]) == (this_week(), True, False)
    assert titles(week) == ["At six", "Today", "In the bank"]
    assert week["tasks"][2]["goalLabel"] == "Be strong"


def test_next_week_reads_as_open_once_it_is(
    tasks_client: TestClient, connection: Connection
) -> None:
    open_next_week(connection)
    next_week = (week_of(today()) + timedelta(weeks=1)).isoformat()

    week = get_week(tasks_client, next_week)

    assert (week["isCurrent"], week["nextWeekOpen"]) == (False, True)
    assert get_week(tasks_client, this_week())["nextWeekOpen"] is True


def test_the_week_shows_how_often_a_task_carried_over(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client)
    for weeks_ago in (2, 1):
        connection.execute(
            text(
                "insert into task_weeks (id, user_id, task_id, week, outcome)"
                " select :id, user_id, id, :week, 'rolled_over' from tasks where id = :task"
            ),
            {
                "id": uuid4(),
                "task": task["id"],
                "week": week_of(today()) - timedelta(weeks=weeks_ago),
            },
        )

    [shown] = get_week(tasks_client, this_week())["tasks"]

    assert shown["carriedOver"] == 2
    edited = tasks_client.patch(f"/api/tasks/{task['id']}", json={"title": task["title"]})
    assert edited.json()["carriedOver"] == 2  # a write's task counts as the week read does
    last_week = (week_of(today()) - timedelta(weeks=1)).isoformat()
    [past] = get_week(tasks_client, last_week)["tasks"]  # the row it rolled over from
    assert (past["weekOutcome"], past["carriedOver"]) == ("rolledOver", 1)


def test_set_aside_rows_and_other_users_tasks_are_not_shown(
    tasks_client: TestClient, connection: Connection
) -> None:
    task = add_task(tasks_client)
    connection.execute(
        text("update task_weeks set outcome = 'set_aside' where task_id = :id"), {"id": task["id"]}
    )
    other = add_other_user(connection)
    theirs = uuid4()
    values = {"id": theirs, "row": uuid4(), "user": other, "week": week_of(today())}
    connection.execute(
        text(
            "insert into tasks (id, user_id, title, origin)"
            " values (:id, :user, 'Theirs', 'by_hand')"
        ),
        values,
    )
    connection.execute(
        text(
            "insert into task_weeks (id, user_id, task_id, week) values (:row, :user, :id, :week)"
        ),
        values,
    )

    assert get_week(tasks_client, this_week())["tasks"] == []


def test_a_week_is_named_by_its_monday(tasks_client: TestClient) -> None:
    tuesday = (week_of(today()) + timedelta(days=1)).isoformat()

    response = tasks_client.get(f"/api/weeks/{tuesday}")

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["path", "week"]


def day_marks(client: TestClient) -> dict[str, Any]:
    return {mark["day"]: mark for mark in get_week(client, this_week())["days"]}


def test_the_week_has_seven_days_with_the_normal_cap(tasks_client: TestClient) -> None:
    marks = get_week(tasks_client, this_week())["days"]

    first = week_of(today())
    assert [mark["day"] for mark in marks] == [
        (first + timedelta(days=n)).isoformat() for n in range(7)
    ]
    assert all(mark["cap"] == 4 and not mark["full"] for mark in marks)


def test_a_day_is_full_at_the_cap(tasks_client: TestClient) -> None:
    day = today().isoformat()
    for n in range(3):
        add_task(tasks_client, title=f"Task {n}", day=day)
    assert not day_marks(tasks_client)[day]["full"]

    add_task(tasks_client, title="Fourth", day=day)

    assert day_marks(tasks_client)[day]["full"]


def test_a_done_task_counts_and_a_dropped_one_does_not(tasks_client: TestClient) -> None:
    day = today().isoformat()
    tasks = [add_task(tasks_client, title=f"Task {n}", day=day) for n in range(4)]
    check_off(tasks_client, tasks[0]["id"])
    assert day_marks(tasks_client)[day]["full"]

    response = tasks_client.post(f"/api/tasks/{tasks[1]['id']}/drop")
    assert response.status_code == 200, response.text

    assert not day_marks(tasks_client)[day]["full"]


def test_changing_intensity_changes_only_the_mark(
    tasks_client: TestClient, connection: Connection
) -> None:
    day = today().isoformat()
    for n in range(3):
        add_task(tasks_client, title=f"Task {n}", day=day)
    before = get_week(tasks_client, this_week())

    connection.execute(text("update users set intensity = 'easing_off'"))
    after = get_week(tasks_client, this_week())

    assert after["tasks"] == before["tasks"]
    assert {mark["cap"] for mark in after["days"]} == {3}
    assert [mark["day"] for mark in after["days"] if mark["full"]] == [day]

    connection.execute(text("update users set intensity = 'going_hard'"))
    assert {mark["cap"] for mark in get_week(tasks_client, this_week())["days"]} == {6}


def quitting_goals(client: TestClient) -> list[Any]:
    found: list[Any] = get_week(client, this_week())["quittingGoals"]
    return found


def test_the_week_carries_each_active_quitting_goals_days(tasks_client: TestClient) -> None:
    goal = create_goal(tasks_client, no_sugar(startDate="2026-11-01"))
    for path, body in [("quit-days", {"held": True}), ("urges", {"level": "some"})]:
        response = tasks_client.put(f"/api/goals/{goal['id']}/{path}/2026-11-17", json=body)
        assert response.status_code == 200, response.text

    [found] = quitting_goals(tasks_client)

    assert (found["id"], found["label"]) == (goal["id"], "No sugar")
    assert [d["day"] for d in found["days"]] == [f"2026-11-{day}" for day in range(16, 23)]
    tuesday = found["days"][1]
    assert (tuesday["held"], tuesday["urge"]) == (True, "some")
    assert all(d["held"] is None for d in found["days"] if d["day"] != "2026-11-17")


def test_a_goal_started_midweek_has_its_days_from_the_start(tasks_client: TestClient) -> None:
    create_goal(tasks_client, no_sugar(startDate="2026-11-18"))

    [found] = quitting_goals(tasks_client)

    assert [d["day"] for d in found["days"]] == [f"2026-11-{day}" for day in range(18, 23)]


def test_paused_and_later_and_building_goals_are_left_out(tasks_client: TestClient) -> None:
    paused = create_goal(tasks_client, no_sugar())
    assert tasks_client.post(f"/api/goals/{paused['id']}/pause").status_code == 200
    create_goal(tasks_client, no_sugar(label="No soda", startDate="2026-11-23"))
    create_goal(tasks_client, lifting())

    assert quitting_goals(tasks_client) == []


# What Today and Week need from the week read alone (#45): each task's and goal's aspiration,
# and whether a task is fixed to its day.


def test_a_goals_task_and_the_goal_name_its_aspiration_and_priority(
    tasks_client: TestClient,
) -> None:
    create_aspiration(tasks_client, "Be fit")
    second = create_aspiration(tasks_client, "Be kind")
    goal = create_goal(tasks_client, lifting(aspirationId=second["id"]))
    add_task(tasks_client, title="Lift", goalId=goal["id"])

    week = get_week(tasks_client, this_week())

    named = {"id": second["id"], "name": "Be kind", "position": 2}
    [lift] = [task for task in week["tasks"] if task["title"] == "Lift"]
    assert lift["aspiration"] == named
    [bar] = week["goals"]
    assert bar["aspiration"] == named


def test_a_loose_task_and_a_goal_with_no_aspiration_name_none(tasks_client: TestClient) -> None:
    goal = create_goal(tasks_client, lifting())
    add_task(tasks_client, title="Lift", goalId=goal["id"])
    add_task(tasks_client, title="Call the vet")

    week = get_week(tasks_client, this_week())

    assert {
        task["title"]: task["aspiration"] for task in week["tasks"] if task["origin"] == "byHand"
    } == {
        "Lift": None,
        "Call the vet": None,
    }
    assert week["goals"][0]["aspiration"] is None


def test_a_retired_aspiration_has_no_priority(tasks_client: TestClient) -> None:
    aspiration = create_aspiration(tasks_client, "Be fit")
    goal = create_goal(tasks_client, lifting(aspirationId=aspiration["id"]))
    add_task(tasks_client, title="Lift", goalId=goal["id"])
    retired = tasks_client.post(
        f"/api/aspirations/{aspiration['id']}/retire", json={"itsWork": "keep"}
    )
    assert retired.status_code == 200, retired.text

    week = get_week(tasks_client, this_week())

    [lift] = [task for task in week["tasks"] if task["title"] == "Lift"]
    assert lift["aspiration"] == {"id": aspiration["id"], "name": "Be fit", "position": None}


def test_a_weekly_or_monthly_items_task_is_fixed_to_its_day(tasks_client: TestClient) -> None:
    create_item(
        tasks_client,
        item(name="Water the plants", schedule={"kind": "weekly", "weekday": "thursday"}),
    )
    create_item(
        tasks_client,
        item(name="Laundry", schedule={"kind": "flexible", "times": 1, "period": "week"}),
    )
    add_task(tasks_client, title="Call the vet")

    week = get_week(tasks_client, this_week())

    fixed = {task["title"]: task["fixedDay"] for task in week["tasks"]}
    assert fixed == {"Water the plants": True, "Laundry": False, "Call the vet": False}


def test_a_task_write_and_the_upcoming_list_carry_both(tasks_client: TestClient) -> None:
    aspiration = create_aspiration(tasks_client, "Be fit")
    goal = create_goal(tasks_client, lifting(aspirationId=aspiration["id"]))

    added = add_task(tasks_client, title="Lift", goalId=goal["id"])
    add_task(tasks_client, title="Waiting", dueDate=(today() + timedelta(days=8)).isoformat())
    upcoming = tasks_client.get("/api/tasks/upcoming").json()["tasks"]

    assert (added["aspiration"]["name"], added["fixedDay"]) == ("Be fit", False)
    assert [(task["aspiration"], task["fixedDay"]) for task in upcoming] == [(None, False)]


def test_a_monthly_items_task_is_fixed_to_its_day(tasks_client: TestClient) -> None:
    create_item(tasks_client, item(name="Pay rent", schedule={"kind": "monthly", "dayOfMonth": 20}))

    [rent] = [
        task for task in get_week(tasks_client, this_week())["tasks"] if task["title"] == "Pay rent"
    ]

    assert rent["fixedDay"] is True


def test_a_fixed_day_task_that_carried_over_is_placed_like_any_task(
    tasks_client: TestClient, connection: Connection
) -> None:
    create_item(
        tasks_client,
        item(name="Water the plants", schedule={"kind": "weekly", "weekday": "thursday"}),
    )
    connection.execute(
        text(
            "insert into task_weeks (id, user_id, task_id, week, outcome)"
            " select :id, user_id, id, :week, 'rolled_over' from tasks"
            " where title = 'Water the plants'"
        ),
        {"id": uuid4(), "week": week_of(today()) - timedelta(weeks=1)},
    )

    [plants] = [
        task
        for task in get_week(tasks_client, this_week())["tasks"]
        if task["title"] == "Water the plants"
    ]

    assert (plants["carriedOver"], plants["fixedDay"]) == (1, False)


def test_an_upcoming_task_names_its_goals_aspiration(tasks_client: TestClient) -> None:
    aspiration = create_aspiration(tasks_client, "Be fit")
    goal = create_goal(tasks_client, lifting(aspirationId=aspiration["id"]))
    add_task(
        tasks_client,
        title="Book a race",
        goalId=goal["id"],
        dueDate=(today() + timedelta(days=40)).isoformat(),
    )

    [waiting] = tasks_client.get("/api/tasks/upcoming").json()["tasks"]

    assert waiting["aspiration"] == {"id": aspiration["id"], "name": "Be fit", "position": 1}


def test_a_recurring_items_task_with_no_goal_names_the_items_aspiration(
    tasks_client: TestClient,
) -> None:
    aspiration = create_aspiration(tasks_client, "Be fit")
    create_item(
        tasks_client,
        item(
            name="Stretch",
            aspirationId=aspiration["id"],
            schedule={"kind": "weekly", "weekday": "thursday"},
        ),
    )
    create_item(
        tasks_client, item(name="Laundry", schedule={"kind": "weekly", "weekday": "thursday"})
    )

    week = get_week(tasks_client, this_week())

    assert {task["title"]: task["aspiration"] for task in week["tasks"]} == {
        "Stretch": {"id": aspiration["id"], "name": "Be fit", "position": 1},
        "Laundry": None,
    }


# nextUp: the one thing Today's last line names (spec `coming-up`)


def next_up(client: TestClient, week: str | None = None) -> Any:
    return get_week(client, week or this_week())["nextUp"]


def test_next_up_is_the_earliest_task_set_to_a_day_or_due_after_today(
    tasks_client: TestClient,
) -> None:
    add_task(tasks_client, title="Due next week", dueDate="2026-11-24")
    add_task(tasks_client, title="Tomorrow", day="2026-11-19")

    assert next_up(tasks_client)["title"] == "Tomorrow"


def test_a_task_later_today_is_never_next_up(tasks_client: TestClient) -> None:
    add_task(tasks_client, title="Later today", day="2026-11-18", dueDate="2026-11-19")
    add_task(tasks_client, title="Due next week", dueDate="2026-11-24")

    assert next_up(tasks_client)["title"] == "Due next week"


def test_next_up_looks_no_further_than_coming_ups_last_week(tasks_client: TestClient) -> None:
    add_task(tasks_client, title="Week 13", dueDate="2027-02-15")

    assert next_up(tasks_client) is None

    add_task(tasks_client, title="Week 12", dueDate="2027-02-14")

    assert next_up(tasks_client)["title"] == "Week 12"


def test_next_up_is_empty_in_another_weeks_read_and_with_nothing_coming(
    tasks_client: TestClient,
) -> None:
    assert next_up(tasks_client) is None

    add_task(tasks_client, title="Next week", day="2026-11-24")

    assert next_up(tasks_client, "2026-11-23") is None
    assert next_up(tasks_client)["title"] == "Next week"


def test_done_dropped_recurring_and_paused_goals_tasks_are_never_next_up(
    tasks_client: TestClient,
) -> None:
    done = add_task(tasks_client, title="Done", day="2026-11-19")
    check_off(tasks_client, done["id"])
    dropped = add_task(tasks_client, title="Dropped", day="2026-11-19")
    assert tasks_client.post(f"/api/tasks/{dropped['id']}/drop").status_code == 200
    create_item(tasks_client, item(schedule={"kind": "weekly", "weekday": "thursday"}))
    goal = create_goal(tasks_client, lifting())
    add_task(tasks_client, title="Paused goal's", goalId=goal["id"], dueDate="2026-11-25")
    assert tasks_client.post(f"/api/goals/{goal['id']}/pause").status_code == 200

    assert next_up(tasks_client) is None


def test_a_task_set_to_a_day_is_next_up_on_that_day_not_its_due_date(
    tasks_client: TestClient,
) -> None:
    add_task(
        tasks_client, title="Set to Thursday next week", day="2026-11-26", dueDate="2026-11-19"
    )
    add_task(tasks_client, title="Friday", day="2026-11-20")

    assert next_up(tasks_client)["title"] == "Friday"
