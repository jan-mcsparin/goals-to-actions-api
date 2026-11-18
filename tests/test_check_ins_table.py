from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.config import FIXED_USER_ID
from app.database import Database
from tests.test_goals_table import add_goal, add_user
from tests.test_milestones_table import add_milestone

ADD_CHECK_IN = text(
    "insert into check_ins (id, user_id, goal_id, milestone_id, outcome, result, checked_in_on)"
    " values (:id, :user_id, :goal_id, :milestone_id, :outcome, :result, :checked_in_on)"
)


def add_check_in(database: Database, goal_id: UUID, **columns: Any) -> UUID:
    check_in_id = uuid4()
    values = {
        "id": check_in_id,
        "user_id": FIXED_USER_ID,
        "goal_id": goal_id,
        "milestone_id": None,
        "outcome": "hit",
        "result": None,
        "checked_in_on": "2026-11-17",
    } | columns
    with database.transaction(FIXED_USER_ID, "check in") as tx:
        tx.execute(ADD_CHECK_IN, values)
    return check_in_id


def test_every_check_in_for_a_milestone_is_kept(database: Database) -> None:
    goal_id = add_goal(database)
    milestone_id = add_milestone(database, goal_id)

    add_check_in(database, goal_id, milestone_id=milestone_id, outcome="not_yet", result="140")
    add_check_in(database, goal_id, milestone_id=milestone_id, outcome="hit", result="155")
    add_check_in(database, goal_id)  # the goal's own line

    with database.read() as tx:
        count = tx.execute(text("select count(*) from check_ins")).scalar()
    assert count == 3


def test_a_check_in_cannot_name_another_goals_milestone(database: Database) -> None:
    goal_id = add_goal(database)
    elsewhere = add_milestone(database, add_goal(database))

    with pytest.raises(IntegrityError, match="check_ins_milestone_of_goal"):
        add_check_in(database, goal_id, milestone_id=elsewhere)


def test_a_check_in_cannot_point_at_another_owners_goal(database: Database) -> None:
    theirs = add_goal(database, add_user(database))

    with pytest.raises(IntegrityError, match="check_ins_goal_same_owner"):
        add_check_in(database, theirs)


def test_an_unknown_outcome_is_refused(database: Database) -> None:
    with pytest.raises(IntegrityError, match="check_ins_outcome_check"):
        add_check_in(database, add_goal(database), outcome="missed")
