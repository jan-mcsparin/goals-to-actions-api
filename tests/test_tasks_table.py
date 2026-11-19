from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.config import FIXED_USER_ID
from app.database import Database
from tests.test_goals_table import add_goal, add_user

ADD_TASK = text(
    "insert into tasks (id, user_id, title, origin, goal_id, recurring_item_id, state,"
    " time_kind, time_of_day, value_logged, completed_at, completed_on, period_start, number)"
    " values (:id, :user_id, :title, :origin, :goal_id, :recurring_item_id, :state,"
    " :time_kind, :time_of_day, :value_logged, :completed_at, :completed_on, :period_start,"
    " :number)"
)


def add_task(database: Database, user_id: UUID = FIXED_USER_ID, **columns: Any) -> UUID:
    task_id = uuid4()
    values = {
        "id": task_id,
        "user_id": user_id,
        "title": "Call the dentist",
        "origin": "by_hand",
        "goal_id": None,
        "recurring_item_id": None,
        "state": "open",
        "time_kind": None,
        "time_of_day": None,
        "value_logged": None,
        "completed_at": None,
        "completed_on": None,
        "period_start": None,
        "number": None,
    } | columns
    with database.transaction(user_id, "add task") as tx:
        tx.execute(ADD_TASK, values)
    return task_id


def session(database: Database, goal_id: UUID, number: int = 1) -> UUID:
    return add_task(
        database, origin="weekly_target", goal_id=goal_id, period_start="2026-11-16", number=number
    )


def test_a_task_can_stand_alone_or_serve_a_goal(database: Database) -> None:
    add_task(database)
    add_task(database, goal_id=add_goal(database), time_kind="at", time_of_day="18:00")

    with database.read() as tx:
        assert tx.execute(text("select count(*) from tasks")).scalar() == 2


def test_a_task_cannot_have_both_a_goal_and_a_recurring_item(database: Database) -> None:
    with pytest.raises(IntegrityError, match="tasks_goal_or_item"):
        add_task(
            database,
            origin="recurring_item",
            goal_id=add_goal(database),
            recurring_item_id=uuid4(),
            period_start="2026-11-16",
            number=1,
        )


def test_a_task_cannot_point_at_another_owners_goal(database: Database) -> None:
    with pytest.raises(IntegrityError, match="tasks_goal_same_owner"):
        add_task(database, goal_id=add_goal(database, add_user(database)))


def test_a_weekly_target_task_needs_a_goal(database: Database) -> None:
    with pytest.raises(IntegrityError, match="tasks_weekly_target_has_goal"):
        add_task(database, origin="weekly_target", period_start="2026-11-16", number=1)


def test_a_task_with_an_item_has_that_origin(database: Database) -> None:
    with pytest.raises(IntegrityError, match="tasks_item_means_its_origin"):
        add_task(database, recurring_item_id=uuid4())


@pytest.mark.parametrize(
    ("column", "value", "constraint"),
    [
        ("state", "skipped", "tasks_state_check"),
        ("title", "  ", "tasks_title_not_blank"),
        ("time_kind", "at", "tasks_time_kind_and_time"),
        ("time_of_day", "18:00", "tasks_time_kind_and_time"),
        ("period_start", "2026-11-16", "tasks_generated_has_period"),
        ("completed_on", "2026-11-18", "tasks_done_has_completion"),
        ("value_logged", 3, "tasks_done_has_completion"),
    ],
)
def test_the_database_refuses_a_task_that_breaks_a_rule(
    database: Database, column: str, value: Any, constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        add_task(database, **{column: value})


def test_an_unknown_origin_is_refused(database: Database) -> None:
    with pytest.raises(IntegrityError, match="tasks_origin_check"):
        add_task(database, origin="planner", period_start="2026-11-16", number=1)


def test_a_done_task_has_its_moment_and_day(database: Database) -> None:
    add_task(
        database,
        state="done",
        completed_at="2026-11-18T07:30:00Z",
        completed_on="2026-11-18",
        value_logged=3.1,
    )
    with pytest.raises(IntegrityError, match="tasks_done_has_completion"):
        add_task(database, state="done")


def test_a_generated_task_is_made_once_even_after_a_delete(database: Database) -> None:
    goal_id = add_goal(database)
    first = session(database, goal_id)
    with database.transaction(FIXED_USER_ID, "delete task") as tx:
        tx.execute(text("update tasks set deleted_at = now() where id = :id"), {"id": first})

    session(database, goal_id, number=2)
    with pytest.raises(IntegrityError, match="tasks_goal_period_number"):
        session(database, goal_id)


def test_a_recurring_task_is_made_once_per_period_and_number(database: Database) -> None:
    item = uuid4()
    columns: dict[str, Any] = {"origin": "recurring_item", "recurring_item_id": item, "number": 1}
    add_task(database, period_start="2026-11-16", **columns)
    with pytest.raises(IntegrityError, match="tasks_item_period_number"):
        add_task(database, period_start="2026-11-16", **columns)
