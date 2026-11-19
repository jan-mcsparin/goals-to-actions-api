"""Writes that take the user lock (renumbering aspirations, writing goals) wait for that
user's row, so two arriving together run one after the other. Needs two real connections,
so it uses the engine; the write under test is rolled back, so nothing is kept."""

from collections.abc import Callable
from datetime import date
from threading import Thread
from uuid import uuid4

import pytest
from sqlalchemy import Connection, Engine, text

from app.aspirations import rules
from app.config import FIXED_USER_ID
from app.database import Database
from app.errors import NotFound
from app.goals import rules as goal_rules
from app.goals.models import GoalEdit, NewGoal, WeeklyTargetInput
from app.milestones import rules as milestone_rules
from app.milestones.models import MilestoneEdit, MilestoneOrder, NewCheckIn, NewMilestone
from app.tasks import rules as task_rules
from app.tasks.models import NewTask

NEW_GOAL = NewGoal(type="oneOff", label="Move house", measurable_line="Keys handed in")


class RollBack(Exception):
    pass


WRITES: dict[str, Callable[[Connection], object]] = {
    "create": lambda tx: rules.create(tx, FIXED_USER_ID, uuid4(), "Be fit", None),
    "reorder": lambda tx: rules.reorder(tx, FIXED_USER_ID, []),
    "retire": lambda tx: rules.retire(tx, FIXED_USER_ID, uuid4(), date(2026, 11, 16), True),
    "bring back": lambda tx: rules.bring_back(tx, FIXED_USER_ID, uuid4()),
    "create goal": lambda tx: goal_rules.create(
        tx, FIXED_USER_ID, uuid4(), NEW_GOAL, date(2026, 11, 16)
    ),
    "update goal": lambda tx: goal_rules.update(
        tx, FIXED_USER_ID, uuid4(), GoalEdit(label="Move", measurable_line="Keys handed in")
    ),
    "set weekly target": lambda tx: goal_rules.set_weekly_target(
        tx,
        FIXED_USER_ID,
        uuid4(),
        WeeklyTargetInput(kind="count", sessions=3, unit="runs"),
        date(2026, 11, 16),
    ),
    "change goal status": lambda tx: goal_rules.change_status(
        tx, FIXED_USER_ID, uuid4(), goal_rules.PAUSE, date(2026, 11, 16)
    ),
    "add milestone": lambda tx: milestone_rules.add(
        tx, FIXED_USER_ID, uuid4(), NewMilestone(goal_id=uuid4(), measurable_line="Bench 155")
    ),
    "update milestone": lambda tx: milestone_rules.update(
        tx, FIXED_USER_ID, uuid4(), MilestoneEdit(measurable_line="Bench 155")
    ),
    "reorder milestones": lambda tx: milestone_rules.reorder(
        tx, FIXED_USER_ID, uuid4(), MilestoneOrder(ids=[])
    ),
    "check in": lambda tx: milestone_rules.check_in(
        tx,
        FIXED_USER_ID,
        uuid4(),
        NewCheckIn(goal_id=uuid4(), milestone_id=None, outcome="hit"),
        date(2026, 11, 16),
    ),
    "keep milestone": lambda tx: milestone_rules.keep(tx, FIXED_USER_ID, uuid4()),
    "add task": lambda tx: task_rules.add(
        tx, FIXED_USER_ID, uuid4(), NewTask(title="Pack"), date(2026, 11, 16)
    ),
}


@pytest.mark.parametrize("write", WRITES.values(), ids=WRITES.keys())
def test_a_renumbering_write_waits_for_the_users_row(
    test_engine: Engine, write: Callable[[Connection], object]
) -> None:
    def write_then_roll_back() -> None:
        try:
            with Database(test_engine).transaction(FIXED_USER_ID, "test the lock") as tx:
                try:
                    write(tx)
                except NotFound:
                    pass
                raise RollBack
        except RollBack:
            pass

    writer = Thread(target=write_then_roll_back)
    with test_engine.connect() as holder:
        # Not `for update`: a create would wait for that anyway, through its foreign key.
        holder.execute(
            text("select id from users where id = :id for no key update"), {"id": FIXED_USER_ID}
        )
        writer.start()
        writer.join(timeout=0.5)
        waited = writer.is_alive()
        holder.rollback()
    writer.join(timeout=5)

    assert waited
    assert not writer.is_alive()
