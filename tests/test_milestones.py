from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from tests.test_aspirations import add_other_user, audit_rows
from tests.test_goals import ZONE, add_goal_for, create_goal, lifting, no_sugar, today


@pytest.fixture
def goals_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


def day(days_from_today: int) -> str:
    return (today() + timedelta(days=days_from_today)).isoformat()


def add_milestone(
    client: TestClient,
    goal_id: str,
    line: str = "Bench 155",
    target_date: str | None = None,
    milestone_id: UUID | None = None,
) -> Any:
    return client.put(
        f"/api/milestones/{milestone_id or uuid4()}",
        json={"goalId": goal_id, "measurableLine": line, "targetDate": target_date},
    )


def page(client: TestClient, goal_id: str) -> Any:
    response = client.get(f"/api/goals/{goal_id}")
    assert response.status_code == 200, response.text
    return response.json()


def lines(goal_page: Any) -> list[tuple[int, str]]:
    return [(m["position"], m["measurableLine"]) for m in goal_page["milestones"]]


# The goal's page


def test_a_goal_with_no_milestones_reads_0_of_1(goals_client: TestClient) -> None:
    goal = create_goal(goals_client, lifting())

    assert page(goals_client, goal["id"]) == {
        "goal": goal,
        "milestones": [],
        "progress": {"hit": 0, "of": 1},
        "latest": None,
    }


# addMilestone


def test_add_puts_the_milestone_last_and_returns_the_page(goals_client: TestClient) -> None:
    goal = create_goal(goals_client, lifting(deadline=day(90)))
    milestone_id = uuid4()
    add_milestone(goals_client, goal["id"], "Bench 135")

    response = add_milestone(goals_client, goal["id"], " Bench 155 ", day(30), milestone_id)

    assert response.status_code == 200, response.text
    added = response.json()
    assert added == page(goals_client, goal["id"])
    assert added["milestones"][1] == {
        "id": str(milestone_id),
        "position": 2,
        "measurableLine": "Bench 155",
        "targetDate": day(30),
        "status": "upcoming",
    }
    assert added["progress"] == {"hit": 0, "of": 3}


def test_a_quitting_goal_has_milestones(goals_client: TestClient) -> None:
    goal = create_goal(goals_client, no_sugar())

    assert add_milestone(goals_client, goal["id"], "30 days").status_code == 200


def test_a_one_off_goal_has_no_milestones(goals_client: TestClient) -> None:
    goal = create_goal(goals_client, no_sugar(type="oneOff"))

    assert add_milestone(goals_client, goal["id"]).status_code == 409


def test_the_same_add_twice_returns_the_page_as_it_is(
    goals_client: TestClient, connection: Connection
) -> None:
    goal = create_goal(goals_client, lifting())
    milestone_id = uuid4()
    first = add_milestone(goals_client, goal["id"], milestone_id=milestone_id).json()

    again = add_milestone(goals_client, goal["id"], "Other", milestone_id=milestone_id).json()

    assert again == first
    assert [row.action for row in audit_rows(connection, milestone_id)] == ["add milestone"]


@pytest.mark.parametrize(
    ("deadline", "target_date"),
    [(None, -1), (60, 61)],
)
def test_a_date_outside_the_goals_start_and_deadline_is_not_allowed(
    goals_client: TestClient, deadline: int | None, target_date: int
) -> None:
    goal = create_goal(goals_client, lifting(deadline=None if deadline is None else day(deadline)))

    response = add_milestone(goals_client, goal["id"], target_date=day(target_date))

    assert response.status_code == 409


def test_dates_on_the_start_and_the_deadline_are_allowed(goals_client: TestClient) -> None:
    goal = create_goal(goals_client, lifting(deadline=day(60)))

    assert add_milestone(goals_client, goal["id"], target_date=day(0)).status_code == 200
    assert add_milestone(goals_client, goal["id"], target_date=day(60)).status_code == 200


def test_another_users_goal_is_not_found(goals_client: TestClient, connection: Connection) -> None:
    theirs = add_goal_for(connection, add_other_user(connection))
    connection.execute(text("update goals set type = 'building' where id = :id"), {"id": theirs})

    assert add_milestone(goals_client, str(theirs)).status_code == 404
    assert add_milestone(goals_client, str(uuid4())).status_code == 404


def test_an_id_already_another_goals_milestone_is_not_allowed(goals_client: TestClient) -> None:
    first = create_goal(goals_client, lifting())
    second = create_goal(goals_client, lifting())
    milestone_id = uuid4()
    add_milestone(goals_client, first["id"], milestone_id=milestone_id)

    response = add_milestone(goals_client, second["id"], milestone_id=milestone_id)

    assert response.status_code == 409


@pytest.mark.parametrize("line", ["", "  ", "nul\x00", "x" * 501])
def test_a_line_that_breaks_the_rules_is_refused(goals_client: TestClient, line: str) -> None:
    goal = create_goal(goals_client, lifting())

    assert add_milestone(goals_client, goal["id"], line).status_code == 422


# updateMilestone


def update_milestone(
    client: TestClient, milestone_id: str, line: str, target_date: str | None
) -> Any:
    return client.patch(
        f"/api/milestones/{milestone_id}",
        json={"measurableLine": line, "targetDate": target_date},
    )


def dates(goal_page: Any) -> list[str | None]:
    return [m["targetDate"] for m in goal_page["milestones"]]


def goal_with_dates(client: TestClient, *offsets: int | None, deadline: int = 90) -> Any:
    goal = create_goal(client, lifting(deadline=day(deadline)))
    for number, offset in enumerate(offsets, start=1):
        add_milestone(client, goal["id"], f"M{number}", None if offset is None else day(offset))
    return page(client, goal["id"])


def test_update_changes_the_line_and_date(goals_client: TestClient) -> None:
    before = goal_with_dates(goals_client, 10)
    milestone = before["milestones"][0]

    response = update_milestone(goals_client, milestone["id"], " Bench 160 ", day(12))

    assert response.status_code == 200, response.text
    assert response.json()["milestones"] == [
        milestone | {"measurableLine": "Bench 160", "targetDate": day(12)}
    ]


def test_moving_a_date_later_pushes_later_dated_milestones_out(goals_client: TestClient) -> None:
    before = goal_with_dates(goals_client, 10, 20, None, 30, deadline=90)
    first, second = before["milestones"][0], before["milestones"][1]

    after = update_milestone(goals_client, second["id"], "M2", day(25)).json()

    assert dates(after) == [day(10), day(25), None, day(35)]
    assert first == after["milestones"][0]


def test_pushed_dates_stop_at_the_deadline(goals_client: TestClient) -> None:
    before = goal_with_dates(goals_client, 10, 50, 58, deadline=60)

    after = update_milestone(goals_client, before["milestones"][0]["id"], "M1", day(20)).json()

    assert dates(after) == [day(20), day(60), day(60)]


def test_moving_a_date_earlier_or_setting_one_moves_nothing_else(
    goals_client: TestClient,
) -> None:
    before = goal_with_dates(goals_client, 20, None, 30)

    earlier = update_milestone(goals_client, before["milestones"][0]["id"], "M1", day(5)).json()
    dated = update_milestone(goals_client, before["milestones"][1]["id"], "M2", day(25)).json()

    assert dates(earlier) == [day(5), None, day(30)]
    assert dates(dated) == [day(5), day(25), day(30)]


def test_editing_a_not_yet_milestone_makes_it_upcoming(
    goals_client: TestClient, connection: Connection
) -> None:
    before = goal_with_dates(goals_client, 10, 20)
    not_yet, hit = before["milestones"]
    connection.execute(
        text("update milestones set status = 'not_yet' where id = :id"), {"id": not_yet["id"]}
    )
    connection.execute(
        text("update milestones set status = 'hit' where id = :id"), {"id": hit["id"]}
    )

    update_milestone(goals_client, not_yet["id"], "M1", day(15))
    after = update_milestone(goals_client, hit["id"], "M2 fixed", day(20)).json()

    assert [m["status"] for m in after["milestones"]] == ["upcoming", "hit"]
    assert connection.execute(text("select count(*) from check_ins")).scalar() == 0


def test_a_date_outside_the_goal_is_not_allowed(goals_client: TestClient) -> None:
    before = goal_with_dates(goals_client, 10, deadline=60)
    milestone_id = before["milestones"][0]["id"]

    assert update_milestone(goals_client, milestone_id, "M1", day(61)).status_code == 409
    assert update_milestone(goals_client, milestone_id, "M1", day(-1)).status_code == 409


def test_update_of_another_users_milestone_is_not_found(
    goals_client: TestClient, connection: Connection
) -> None:
    other_user = add_other_user(connection)
    theirs = add_goal_for(connection, other_user)
    connection.execute(text("update goals set type = 'building' where id = :id"), {"id": theirs})
    their_milestone = uuid4()
    connection.execute(
        text(
            "insert into milestones (id, user_id, goal_id, goal_type, position, measurable_line)"
            " values (:id, :user_id, :goal_id, 'building', 1, 'Theirs')"
        ),
        {"id": their_milestone, "user_id": other_user, "goal_id": theirs},
    )

    assert update_milestone(goals_client, str(their_milestone), "Mine", None).status_code == 404
    assert update_milestone(goals_client, str(uuid4()), "Mine", None).status_code == 404


def test_a_goals_deadline_cannot_move_before_a_milestones_date(
    goals_client: TestClient,
) -> None:
    before = goal_with_dates(goals_client, 30, deadline=60)
    goal = before["goal"]
    body = {"label": goal["label"], "measurableLine": goal["measurableLine"]}

    too_early = goals_client.patch(f"/api/goals/{goal['id']}", json=body | {"deadline": day(29)})
    on_it = goals_client.patch(f"/api/goals/{goal['id']}", json=body | {"deadline": day(30)})

    assert too_early.status_code == 409
    assert on_it.status_code == 200


# reorderMilestones


def reorder(client: TestClient, goal_id: str, ids: list[str]) -> Any:
    return client.post(f"/api/goals/{goal_id}/milestones/reorder", json={"ids": ids})


def test_reorder_puts_the_milestones_in_the_order_given(goals_client: TestClient) -> None:
    before = goal_with_dates(goals_client, None, None, None)
    first, second, third = (m["id"] for m in before["milestones"])

    response = reorder(goals_client, before["goal"]["id"], [third, first, second])

    assert response.status_code == 200, response.text
    assert lines(response.json()) == [(1, "M3"), (2, "M1"), (3, "M2")]


@pytest.mark.parametrize("which", ["missing", "repeated", "unknown"])
def test_reorder_must_name_each_milestone_once(goals_client: TestClient, which: str) -> None:
    before = goal_with_dates(goals_client, None, None)
    first, second = (m["id"] for m in before["milestones"])
    ids = {
        "missing": [first],
        "repeated": [first, second, first],
        "unknown": [first, str(uuid4())],
    }[which]

    assert reorder(goals_client, before["goal"]["id"], ids).status_code == 409
    assert lines(page(goals_client, before["goal"]["id"])) == [(1, "M1"), (2, "M2")]


def test_reorder_of_another_users_goal_is_not_found(
    goals_client: TestClient, connection: Connection
) -> None:
    theirs = add_goal_for(connection, add_other_user(connection))

    assert reorder(goals_client, str(theirs), []).status_code == 404
