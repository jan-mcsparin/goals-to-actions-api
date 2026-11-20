"""The rules the quit_days and urge_ratings tables keep themselves."""

from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.config import FIXED_USER_ID
from app.database import Database
from tests.test_goals_table import add_goal, add_user

ADD_QUIT_DAY = text(
    "insert into quit_days (id, user_id, goal_id, day, held)"
    " values (:id, :user_id, :goal_id, :day, :held)"
)
ADD_URGE = text(
    "insert into urge_ratings (id, user_id, goal_id, rated_on, level)"
    " values (:id, :user_id, :goal_id, :rated_on, :level)"
)


def add_quit_day(database: Database, goal_id: UUID, **columns: Any) -> UUID:
    row_id = uuid4()
    values = {
        "id": row_id,
        "user_id": FIXED_USER_ID,
        "goal_id": goal_id,
        "day": "2026-11-17",
        "held": True,
    } | columns
    with database.transaction(FIXED_USER_ID, "answer quit day") as tx:
        tx.execute(ADD_QUIT_DAY, values)
    return row_id


def add_urge(database: Database, goal_id: UUID, **columns: Any) -> UUID:
    row_id = uuid4()
    values = {
        "id": row_id,
        "user_id": FIXED_USER_ID,
        "goal_id": goal_id,
        "rated_on": "2026-11-17",
        "level": "low",
    } | columns
    with database.transaction(FIXED_USER_ID, "rate urge") as tx:
        tx.execute(ADD_URGE, values)
    return row_id


def quitting(database: Database) -> UUID:
    return add_goal(database, type="quitting")


def test_a_quitting_goal_has_answers_and_urge_ratings(database: Database) -> None:
    goal_id = quitting(database)

    add_quit_day(database, goal_id)
    add_quit_day(database, goal_id, day="2026-11-18", held=False)
    for level, day in [("low", "17"), ("some", "18"), ("strong", "19")]:
        add_urge(database, goal_id, level=level, rated_on=f"2026-11-{day}")


@pytest.mark.parametrize("goal_type", ["building", "one_off"])
def test_only_a_quitting_goal_has_them(database: Database, goal_type: str) -> None:
    goal_id = add_goal(database, type=goal_type)

    with pytest.raises(IntegrityError, match="quit_days_quitting_goal_same_owner"):
        add_quit_day(database, goal_id)
    with pytest.raises(IntegrityError, match="urge_ratings_quitting_goal_same_owner"):
        add_urge(database, goal_id)


def test_they_cannot_point_at_another_owners_goal(database: Database) -> None:
    theirs = add_goal(database, add_user(database), type="quitting")

    with pytest.raises(IntegrityError, match="quit_days_quitting_goal_same_owner"):
        add_quit_day(database, theirs)
    with pytest.raises(IntegrityError, match="urge_ratings_quitting_goal_same_owner"):
        add_urge(database, theirs)


def test_one_live_answer_per_goal_per_day(database: Database) -> None:
    goal_id = quitting(database)
    first = add_quit_day(database, goal_id)

    with pytest.raises(IntegrityError, match="quit_days_one_per_day"):
        add_quit_day(database, goal_id, held=False)

    with database.transaction(FIXED_USER_ID, "clear quit day") as tx:
        tx.execute(text("update quit_days set deleted_at = now() where id = :id"), {"id": first})
    add_quit_day(database, goal_id, held=False)


def test_one_live_rating_per_goal_per_day(database: Database) -> None:
    goal_id = quitting(database)
    first = add_urge(database, goal_id)

    with pytest.raises(IntegrityError, match="urge_ratings_one_per_day"):
        add_urge(database, goal_id, level="strong")

    with database.transaction(FIXED_USER_ID, "clear urge rating") as tx:
        tx.execute(text("update urge_ratings set deleted_at = now() where id = :id"), {"id": first})
    add_urge(database, goal_id, level="strong")


def test_an_urge_is_low_some_or_strong(database: Database) -> None:
    with pytest.raises(IntegrityError, match="urge_ratings_level_check"):
        add_urge(database, quitting(database), level="none")


def test_both_are_audited(database: Database) -> None:
    goal_id = quitting(database)
    answer = add_quit_day(database, goal_id)
    urge = add_urge(database, goal_id)

    with database.read() as connection:
        actions = {
            row.table_name: row.action
            for row in connection.execute(
                text("select table_name, action from audit_log where row_id in (:a, :u)"),
                {"a": answer, "u": urge},
            )
        }
    assert actions == {"quit_days": "answer quit day", "urge_ratings": "rate urge"}
