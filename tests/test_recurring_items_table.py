from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.config import FIXED_USER_ID
from app.database import Database
from tests.test_goals_table import add_aspiration, add_goal, add_user

ADD_ITEM = text(
    "insert into recurring_items (id, user_id, name, aspiration_id, from_goal_id, schedule_kind,"
    " weekday, day_of_month, times, period, starts_on, active) values (:id, :user_id, :name,"
    " :aspiration_id, :from_goal_id, :schedule_kind, :weekday, :day_of_month, :times, :period,"
    " :starts_on, :active)"
)

WEEKLY = {"schedule_kind": "weekly", "weekday": 2}
MONTHLY = {"schedule_kind": "monthly", "day_of_month": 1}
FLEXIBLE = {"schedule_kind": "flexible", "times": 3, "period": "week"}
NO_SCHEDULE: dict[str, Any] = {"weekday": None, "day_of_month": None, "times": None, "period": None}


def add_item(database: Database, user_id: UUID = FIXED_USER_ID, **columns: Any) -> UUID:
    item_id = uuid4()
    values = (
        {
            "id": item_id,
            "user_id": user_id,
            "name": "Take out the trash",
            "aspiration_id": None,
            "from_goal_id": None,
            "starts_on": "2026-11-16",
            "active": True,
        }
        | NO_SCHEDULE
        | WEEKLY
        | columns
    )
    with database.transaction(user_id, "create recurring item") as tx:
        tx.execute(ADD_ITEM, values)
    return item_id


@pytest.mark.parametrize("schedule", [WEEKLY, MONTHLY, FLEXIBLE])
def test_an_item_of_each_kind_can_be_added(database: Database, schedule: dict[str, Any]) -> None:
    add_item(database, **(NO_SCHEDULE | schedule))


@pytest.mark.parametrize("period", ["two_weeks", "month"])
def test_a_longer_period_is_once(database: Database, period: str) -> None:
    once: dict[str, Any] = NO_SCHEDULE | {"schedule_kind": "flexible", "times": 1, "period": period}
    add_item(database, **once)

    with pytest.raises(IntegrityError, match="recurring_items_once_in_a_longer_period"):
        add_item(database, **(once | {"times": 2}))


@pytest.mark.parametrize(
    "columns",
    [
        {**WEEKLY, "weekday": None},
        {**WEEKLY, "day_of_month": 1},
        {**WEEKLY, "times": 1},
        {**WEEKLY, "period": "week"},
        {**MONTHLY, "day_of_month": None},
        {**MONTHLY, "weekday": 2},
        {**MONTHLY, "times": 1},
        {**MONTHLY, "period": "week"},
        {**FLEXIBLE, "times": None},
        {**FLEXIBLE, "period": None},
        {**FLEXIBLE, "weekday": 2},
        {**FLEXIBLE, "day_of_month": 1},
    ],
)
def test_the_schedule_fits_its_kind(database: Database, columns: dict[str, Any]) -> None:
    with pytest.raises(IntegrityError, match="recurring_items_schedule_fits_kind"):
        add_item(database, **(NO_SCHEDULE | columns))


@pytest.mark.parametrize(
    ("columns", "constraint"),
    [
        ({"weekday": 0}, "recurring_items_weekday_check"),
        ({"weekday": 8}, "recurring_items_weekday_check"),
        ({**MONTHLY, "weekday": None, "day_of_month": 29}, "recurring_items_day_of_month_check"),
        ({**FLEXIBLE, "weekday": None, "times": 7}, "recurring_items_times_check"),
        ({**FLEXIBLE, "weekday": None, "times": 0}, "recurring_items_times_check"),
        (
            {**FLEXIBLE, "weekday": None, "times": 1, "period": "year"},
            "recurring_items_period_check",
        ),
        ({"schedule_kind": "yearly"}, "recurring_items_schedule_kind_check"),
        ({"name": "  "}, "recurring_items_name_not_blank"),
    ],
)
def test_the_rules_are_kept(database: Database, columns: dict[str, Any], constraint: str) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        add_item(database, **columns)


def test_an_item_can_sit_under_its_owners_aspiration_and_continue_its_goal(
    database: Database,
) -> None:
    add_item(
        database,
        aspiration_id=add_aspiration(database, FIXED_USER_ID),
        from_goal_id=add_goal(database, status="reached", ended_on="2026-11-18"),
    )


def test_an_item_cannot_sit_under_another_owners_aspiration(database: Database) -> None:
    theirs = add_aspiration(database, add_user(database))

    with pytest.raises(IntegrityError, match="recurring_items_aspiration_same_owner"):
        add_item(database, aspiration_id=theirs)


def test_an_item_cannot_continue_another_owners_goal(database: Database) -> None:
    theirs = add_goal(database, add_user(database))

    with pytest.raises(IntegrityError, match="recurring_items_from_goal_same_owner"):
        add_item(database, from_goal_id=theirs)


def test_a_task_cannot_point_at_another_owners_item(database: Database) -> None:
    theirs = add_item(database, add_user(database))

    with pytest.raises(IntegrityError, match="tasks_item_same_owner"):
        with database.transaction(FIXED_USER_ID, "add task") as tx:
            tx.execute(
                text(
                    "insert into tasks (id, user_id, title, origin, recurring_item_id,"
                    " period_start, number) values (:id, :user_id, 'Trash', 'recurring_item',"
                    " :item, '2026-11-16', 1)"
                ),
                {"id": uuid4(), "user_id": FIXED_USER_ID, "item": theirs},
            )
