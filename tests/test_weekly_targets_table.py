from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.config import FIXED_USER_ID
from app.database import Database
from tests.test_goals_table import add_goal, add_user

ADD_TARGET = text(
    "insert into weekly_targets (id, user_id, goal_id, kind, sessions, amount, unit,"
    " effective_from) values (:id, :user_id, :goal_id, :kind, :sessions, :amount, :unit,"
    " :effective_from)"
)


def add_target(database: Database, goal_id: UUID, **columns: Any) -> UUID:
    target_id = uuid4()
    values = {
        "id": target_id,
        "user_id": FIXED_USER_ID,
        "goal_id": goal_id,
        "kind": "count",
        "sessions": 3,
        "amount": None,
        "unit": "lifting sessions",
        "effective_from": "2026-11-16",
    } | columns
    with database.transaction(FIXED_USER_ID, "set weekly target") as tx:
        tx.execute(ADD_TARGET, values)
    return target_id


def test_count_and_amount_targets_can_be_added(database: Database) -> None:
    goal_id = add_goal(database)

    add_target(database, goal_id)
    add_target(
        database, goal_id, kind="amount", sessions=4, amount=25, unit="miles",
        effective_from="2026-11-23",
    )  # fmt: skip


@pytest.mark.parametrize("goal_type", ["quitting", "one_off"])
def test_only_a_building_goal_has_targets(database: Database, goal_type: str) -> None:
    goal_id = add_goal(database, type=goal_type)

    with pytest.raises(IntegrityError, match="weekly_targets_building_goal_same_owner"):
        add_target(database, goal_id)


def test_a_target_cannot_point_at_another_owners_goal(database: Database) -> None:
    theirs = add_goal(database, add_user(database))

    with pytest.raises(IntegrityError, match="weekly_targets_building_goal_same_owner"):
        add_target(database, theirs)


def test_one_row_per_goal_per_week(database: Database) -> None:
    goal_id = add_goal(database)
    add_target(database, goal_id)

    with pytest.raises(IntegrityError, match="weekly_targets_one_per_week"):
        add_target(database, goal_id, sessions=4)


@pytest.mark.parametrize(
    ("columns", "constraint"),
    [
        ({"effective_from": "2026-11-17"}, "weekly_targets_week_is_a_monday"),
        ({"sessions": 0}, "weekly_targets_sessions_check"),
        ({"sessions": 15}, "weekly_targets_sessions_check"),
        ({"kind": "time"}, "weekly_targets_kind_check"),
        ({"kind": "count", "amount": 10}, "weekly_targets_amount_agrees"),
        ({"kind": "amount", "amount": None}, "weekly_targets_amount_agrees"),
        ({"kind": "amount", "amount": 0}, "weekly_targets_amount_agrees"),
        ({"unit": " "}, "weekly_targets_unit_not_blank"),
    ],
)
def test_the_rules_are_kept(database: Database, columns: dict[str, Any], constraint: str) -> None:
    goal_id = add_goal(database)

    with pytest.raises(IntegrityError, match=constraint):
        add_target(database, goal_id, **columns)
