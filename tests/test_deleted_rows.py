"""No read shows a deleted row (spec `delete`). One of everything is made, some of it is
deleted, and then every read and every link between rows is checked."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from tests.test_aspirations import create as create_aspiration
from tests.test_check_ins import check_in
from tests.test_check_off import check_off
from tests.test_goal_sessions import WEEK, sessions
from tests.test_goals import ZONE, create_goal, lifting, no_sugar, today
from tests.test_item_tasks import WEDNESDAY, item_tasks
from tests.test_milestones import add_milestone, page
from tests.test_quit_days import answer
from tests.test_recurring_items import create as create_item
from tests.test_recurring_items import item
from tests.test_tasks import add_task

# Every table whose rows can be deleted. A new one fails the test below until its delete
# (or the delete of what it belongs to) is handled and it's added here.
DELETABLE = {
    "aspirations",
    "goals",
    "weekly_targets",
    "milestones",
    "check_ins",
    "tasks",
    "task_weeks",
    "recurring_items",
    "quit_days",
    "urge_ratings",
    "users",
    "sessions",
    "sign_in_codes",
    "passkeys",
}

# Each foreign key's first column and the table it points at, users left out.
LINKS = text(
    """
    select child.relname as child, attribute.attname as link, parent.relname as parent
    from pg_constraint
    join pg_class child on child.oid = pg_constraint.conrelid
    join pg_class parent on parent.oid = pg_constraint.confrelid
    join pg_attribute attribute
      on attribute.attrelid = child.oid and attribute.attnum = pg_constraint.conkey[1]
    where pg_constraint.contype = 'f' and parent.relname <> 'users'
    """
)


@pytest.fixture
def zoned_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


def one_of_everything_with_some_deleted(client: TestClient) -> None:
    aspiration = create_aspiration(client, "Be fit")
    kept_goal = create_goal(client, lifting(aspirationId=aspiration["id"]))
    check_off(client, sessions(client, WEEK)[0]["id"])
    add_milestone(client, kept_goal["id"], "Bench 135")
    add_milestone(client, kept_goal["id"], "Bench 145")
    first, second = (m["id"] for m in page(client, kept_goal["id"])["milestones"])
    assert check_in(client, kept_goal["id"], first, result="Bench 137").status_code == 200
    quitting = create_goal(client, no_sugar(aspirationId=aspiration["id"]))
    assert answer(client, quitting["id"], today().isoformat(), True).status_code == 200
    one_off = create_goal(
        client, {"type": "oneOff", "label": "Move house", "measurableLine": "Keys handed in"}
    )
    add_task(client, title="Pack", goalId=one_off["id"])
    reached = create_goal(client, lifting(label="Run"))
    client.post(f"/api/goals/{reached['id']}/mark-reached")
    create_item(
        client,
        item(
            name="Running",
            schedule={"kind": "flexible", "times": 2, "period": "week"},
            fromGoalId=reached["id"],
            startsOn=WEDNESDAY,
        ),
    )
    stretch = create_item(
        client,
        item(
            name="Stretch",
            schedule={"kind": "flexible", "times": 3, "period": "week"},
            aspirationId=aspiration["id"],
            startsOn=WEDNESDAY,
        ),
    )
    stretches = [task for task in item_tasks(client, WEEK) if task["title"] == "Stretch"]
    check_off(client, stretches[0]["id"])
    mistake = add_task(client, title="Call the dentist", plannedDay=today().isoformat())

    for path in (
        f"/api/milestones/{first}",
        f"/api/tasks/{mistake['id']}",
        f"/api/recurring-items/{stretch['id']}",
        f"/api/goals/{reached['id']}",
        f"/api/goals/{one_off['id']}",
        f"/api/aspirations/{aspiration['id']}",
    ):
        assert client.delete(path).status_code in (200, 204), path
    assert second  # the kept goal still has a milestone


def deleted_ids(connection: Connection) -> set[str]:
    return {
        str(row_id)
        for table in DELETABLE
        for row_id in connection.execute(
            text(f"select id from {table} where deleted_at is not null")
        ).scalars()
    }


def strings_in(found: Any) -> Iterator[str]:
    if isinstance(found, dict):
        for value in found.values():
            yield from strings_in(value)
    elif isinstance(found, list):
        for value in found:
            yield from strings_in(value)
    elif isinstance(found, str):
        yield found


def every_read(client: TestClient) -> list[Any]:
    goals = client.get("/api/goals").json()
    return [
        client.get("/api/aspirations").json(),
        goals,
        *(client.get(f"/api/goals/{goal['id']}").json() for goal in goals["goals"]),
        client.get("/api/recurring-items").json(),
        client.get(f"/api/weeks/{WEEK}").json(),
        client.get("/api/tasks/upcoming").json(),
    ]


def test_every_deletable_table_is_known(connection: Connection) -> None:
    tables = connection.execute(
        text(
            "select table_name from information_schema.columns"
            " where table_schema = 'public' and column_name = 'deleted_at'"
        )
    ).scalars()

    assert set(tables) == DELETABLE


def test_no_read_shows_a_deleted_row(zoned_client: TestClient, connection: Connection) -> None:
    one_of_everything_with_some_deleted(zoned_client)
    hidden = deleted_ids(connection)
    assert len(hidden) > 10

    shown = {value for read in every_read(zoned_client) for value in strings_in(read)}

    assert shown & hidden == set()


def test_no_live_row_points_at_a_deleted_one(
    zoned_client: TestClient, connection: Connection
) -> None:
    one_of_everything_with_some_deleted(zoned_client)

    dangling = {
        f"{link.child}.{link.link}": connection.execute(
            text(
                f"select count(*) from {link.child} child join {link.parent} parent"
                f" on parent.id = child.{link.link}"
                " where child.deleted_at is null and parent.deleted_at is not null"
            )
        ).scalar_one()
        for link in connection.execute(LINKS)
    }

    assert {link: count for link, count in dangling.items() if count} == {}
    assert "tasks.goal_id" in dangling
