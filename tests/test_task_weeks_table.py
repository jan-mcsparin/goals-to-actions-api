from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.config import FIXED_USER_ID
from app.database import Database
from tests.test_goals_table import add_user
from tests.test_tasks_table import add_task

ADD_ROW = text(
    "insert into task_weeks (id, user_id, task_id, week, planned_day, placed_by_hand, outcome)"
    " values (:id, :user_id, :task_id, :week, :planned_day, :placed_by_hand, :outcome)"
)
DONE: dict[str, Any] = {
    "state": "done",
    "completed_at": "2026-11-18T15:00:00Z",
    "completed_on": "2026-11-18",
}


def add_row(
    database: Database, task_id: UUID, user_id: UUID = FIXED_USER_ID, **columns: Any
) -> UUID:
    row_id = uuid4()
    values = {
        "id": row_id,
        "user_id": user_id,
        "task_id": task_id,
        "week": "2026-11-16",
        "planned_day": None,
        "placed_by_hand": False,
        "outcome": None,
    } | columns
    with database.transaction(user_id, "add task") as tx:
        tx.execute(ADD_ROW, values)
    return row_id


def test_a_task_is_in_play_one_week_and_closed_in_others(database: Database) -> None:
    task_id = add_task(database)
    add_row(database, task_id, week="2026-11-09", outcome="rolled_over")
    add_row(database, task_id, planned_day="2026-11-18", placed_by_hand=True)

    with database.read() as tx:
        assert tx.execute(text("select count(*) from task_weeks")).scalar() == 2


@pytest.mark.parametrize(
    ("columns", "constraint"),
    [
        ({"week": "2026-11-17"}, "task_weeks_week_is_monday"),
        ({"planned_day": "2026-11-23"}, "task_weeks_day_in_week"),
        ({"planned_day": "2026-11-15"}, "task_weeks_day_in_week"),
        ({"placed_by_hand": True}, "task_weeks_placed_on_a_day"),
        ({"outcome": "skipped"}, "task_weeks_outcome_check"),
    ],
)
def test_the_database_refuses_a_row_that_breaks_a_rule(
    database: Database, columns: dict[str, Any], constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        add_row(database, add_task(database), **columns)


def test_a_task_has_one_row_per_week(database: Database) -> None:
    task_id = add_task(database)
    add_row(database, task_id, outcome="set_aside")
    with pytest.raises(IntegrityError, match="task_weeks_one_per_week"):
        add_row(database, task_id, outcome="done")


def test_a_task_has_one_row_in_play(database: Database) -> None:
    task_id = add_task(database)
    add_row(database, task_id)
    with pytest.raises(IntegrityError, match="task_weeks_one_in_play"):
        add_row(database, task_id, week="2026-11-23")


def test_a_row_cannot_point_at_another_owners_task(database: Database) -> None:
    theirs = add_task(database, add_user(database))
    with pytest.raises(IntegrityError, match="task_weeks_task_same_owner"):
        add_row(database, theirs)


def test_a_finished_task_cannot_have_a_row_in_play(database: Database) -> None:
    for state in ("dropped", "lapsed"):
        task_id = add_task(database, state=state)
        with pytest.raises(IntegrityError, match="task_rows_agree"):
            add_row(database, task_id)


def test_a_done_tasks_last_row_is_done(database: Database) -> None:
    with pytest.raises(IntegrityError, match="task_rows_agree"):
        add_task(database, **DONE)

    task_id = add_task(database)
    add_row(database, task_id, week="2026-11-09", outcome="done")
    with database.transaction(FIXED_USER_ID, "check off task") as tx:
        tx.execute(
            text(
                "update tasks set state = 'done', completed_at = now(),"
                " completed_on = '2026-11-13' where id = :id"
            ),
            {"id": task_id},
        )
    with pytest.raises(IntegrityError, match="task_rows_agree"):
        add_row(database, task_id, outcome="rolled_over")


def test_task_and_row_may_disagree_until_the_transaction_ends(database: Database) -> None:
    task_id = add_task(database)
    row_id = add_row(database, task_id)

    with database.transaction(FIXED_USER_ID, "check off task") as tx:
        tx.execute(
            text(
                "update tasks set state = 'done', completed_at = now(),"
                " completed_on = '2026-11-18' where id = :id"
            ),
            {"id": task_id},
        )
        tx.execute(text("update task_weeks set outcome = 'done' where id = :id"), {"id": row_id})

    with pytest.raises(IntegrityError, match="task_rows_agree"):
        with database.transaction(FIXED_USER_ID, "uncheck task") as tx:
            tx.execute(text("update task_weeks set outcome = null where id = :id"), {"id": row_id})
