from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.config import FIXED_USER_ID
from app.database import Database
from tests.test_goals_table import add_goal, add_user

ADD_MILESTONE = text(
    "insert into milestones (id, user_id, goal_id, goal_type, position, measurable_line,"
    " target_date, status) values (:id, :user_id, :goal_id, :goal_type, :position,"
    " :measurable_line, :target_date, :status)"
)


def add_milestone(database: Database, goal_id: UUID, **columns: Any) -> UUID:
    milestone_id = uuid4()
    values = {
        "id": milestone_id,
        "user_id": FIXED_USER_ID,
        "goal_id": goal_id,
        "goal_type": "building",
        "position": 1,
        "measurable_line": "Bench 155",
        "target_date": None,
        "status": "upcoming",
    } | columns
    with database.transaction(FIXED_USER_ID, "add milestone") as tx:
        tx.execute(ADD_MILESTONE, values)
    return milestone_id


@pytest.mark.parametrize("goal_type", ["building", "quitting"])
def test_building_and_quitting_goals_have_milestones(database: Database, goal_type: str) -> None:
    goal_id = add_goal(database, type=goal_type)

    add_milestone(database, goal_id, goal_type=goal_type, target_date="2026-12-01")


def test_a_one_off_goal_has_no_milestones(database: Database) -> None:
    goal_id = add_goal(database, type="one_off")

    with pytest.raises(IntegrityError, match="milestones_goal_type_check"):
        add_milestone(database, goal_id, goal_type="one_off")
    with pytest.raises(IntegrityError, match="milestones_goal_has_milestones_same_owner"):
        add_milestone(database, goal_id, goal_type="building")


def test_a_milestone_cannot_point_at_another_owners_goal(database: Database) -> None:
    theirs = add_goal(database, add_user(database))

    with pytest.raises(IntegrityError, match="milestones_goal_has_milestones_same_owner"):
        add_milestone(database, theirs)


def test_two_milestones_of_a_goal_cannot_share_a_position(database: Database) -> None:
    goal_id = add_goal(database)
    add_milestone(database, goal_id)

    with pytest.raises(IntegrityError, match="milestones_position_unique"):
        add_milestone(database, goal_id)


def test_another_goal_can_use_the_same_position(database: Database) -> None:
    add_milestone(database, add_goal(database))
    add_milestone(database, add_goal(database))


def test_one_statement_can_swap_two_positions(database: Database) -> None:
    goal_id = add_goal(database)
    first = add_milestone(database, goal_id, position=1)
    second = add_milestone(database, goal_id, position=2)

    with database.transaction(FIXED_USER_ID, "reorder milestones") as tx:
        tx.execute(text("update milestones set position = 3 - position"))
        rows = tx.execute(text("select id, position from milestones")).all()

    assert {row.id: row.position for row in rows} == {first: 2, second: 1}


@pytest.mark.parametrize(
    ("columns", "constraint"),
    [
        ({"position": 0}, "milestones_position_check"),
        ({"measurable_line": " "}, "milestones_measurable_line_not_blank"),
        ({"status": "missed"}, "milestones_status_check"),
    ],
)
def test_the_rules_are_kept(database: Database, columns: dict[str, Any], constraint: str) -> None:
    goal_id = add_goal(database)

    with pytest.raises(IntegrityError, match=constraint):
        add_milestone(database, goal_id, **columns)


def test_hit_and_not_yet_are_statuses(database: Database) -> None:
    goal_id = add_goal(database)
    add_milestone(database, goal_id, position=1, status="hit")
    add_milestone(database, goal_id, position=2, status="not_yet")
