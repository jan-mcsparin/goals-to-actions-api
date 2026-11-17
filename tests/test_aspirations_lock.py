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
from app.goals.models import NewGoal

NEW_GOAL = NewGoal(type="oneOff", label="Move house", measurable_line="Keys handed in")


class RollBack(Exception):
    pass


WRITES: dict[str, Callable[[Connection], object]] = {
    "create": lambda tx: rules.create(tx, FIXED_USER_ID, uuid4(), "Be fit", None),
    "reorder": lambda tx: rules.reorder(tx, FIXED_USER_ID, []),
    "retire": lambda tx: rules.retire(tx, FIXED_USER_ID, uuid4(), date(2026, 11, 16)),
    "bring back": lambda tx: rules.bring_back(tx, FIXED_USER_ID, uuid4()),
    "create goal": lambda tx: goal_rules.create(
        tx, FIXED_USER_ID, uuid4(), NEW_GOAL, date(2026, 11, 16)
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
