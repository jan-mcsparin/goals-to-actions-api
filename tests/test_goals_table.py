from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.config import FIXED_USER_ID
from app.database import Database

ADD_GOAL = text(
    "insert into goals (id, user_id, aspiration_id, type, label, measurable_line, start_date,"
    " deadline, status, ended_on) values (:id, :user_id, :aspiration_id, :type, :label,"
    " :measurable_line, :start_date, :deadline, :status, :ended_on)"
)


def add_goal(database: Database, user_id: UUID = FIXED_USER_ID, **columns: Any) -> UUID:
    goal_id = uuid4()
    values = {
        "id": goal_id,
        "user_id": user_id,
        "aspiration_id": None,
        "type": "building",
        "label": "Be strong",
        "measurable_line": "Deadlift 1.5x bodyweight",
        "start_date": "2026-11-16",
        "deadline": None,
        "status": "active",
        "ended_on": None,
    } | columns
    with database.transaction(user_id, "create goal") as tx:
        tx.execute(ADD_GOAL, values)
    return goal_id


def add_user(database: Database) -> UUID:
    user_id = uuid4()
    with database.transaction(user_id, "add user") as tx:
        tx.execute(text("insert into users (id) values (:id)"), {"id": user_id})
    return user_id


def add_aspiration(database: Database, user_id: UUID) -> UUID:
    aspiration_id = uuid4()
    with database.transaction(user_id, "create aspiration") as tx:
        tx.execute(
            text(
                "insert into aspirations (id, user_id, name, position)"
                " values (:id, :user_id, 'Be fit', 1)"
            ),
            {"id": aspiration_id, "user_id": user_id},
        )
    return aspiration_id


def test_a_goal_of_each_type_can_be_added(database: Database) -> None:
    for goal_type in ("building", "quitting", "one_off"):
        add_goal(database, type=goal_type)


def test_a_goal_can_sit_under_its_owners_aspiration(database: Database) -> None:
    add_goal(database, aspiration_id=add_aspiration(database, FIXED_USER_ID))


def test_a_goal_cannot_sit_under_another_owners_aspiration(database: Database) -> None:
    theirs = add_aspiration(database, add_user(database))

    with pytest.raises(IntegrityError, match="goals_aspiration_same_owner"):
        add_goal(database, aspiration_id=theirs)


@pytest.mark.parametrize(
    ("columns", "constraint"),
    [
        ({"type": "habit"}, "goals_type_check"),
        ({"status": "missed", "ended_on": "2026-11-16"}, "goals_status_check"),
        ({"label": "  "}, "goals_label_not_blank"),
        ({"measurable_line": ""}, "goals_measurable_line_not_blank"),
        ({"deadline": "2026-11-15"}, "goals_deadline_not_before_start"),
        ({"status": "active", "ended_on": "2026-11-16"}, "goals_ended_on_agrees"),
        ({"status": "paused", "ended_on": "2026-11-16"}, "goals_ended_on_agrees"),
        ({"status": "reached", "ended_on": None}, "goals_ended_on_agrees"),
        ({"status": "ended", "ended_on": None}, "goals_ended_on_agrees"),
    ],
)
def test_the_rules_are_kept(database: Database, columns: dict[str, Any], constraint: str) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        add_goal(database, **columns)


def test_a_deadline_on_the_start_date_is_allowed(database: Database) -> None:
    add_goal(database, deadline="2026-11-16")


def test_reached_and_ended_goals_have_an_end_day(database: Database) -> None:
    add_goal(database, status="reached", ended_on="2026-11-20")
    add_goal(database, status="ended", ended_on="2026-11-20")
