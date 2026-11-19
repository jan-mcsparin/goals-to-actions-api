"""The planner (ADR-008). `planner` (#10) fills this in: placing recurring work on days."""

from datetime import date
from uuid import UUID

from sqlalchemy import Connection


def place_new_work(
    connection: Connection, user_id: UUID, task_ids: list[UUID], first_day: date
) -> None:
    """Called with the tasks a week's opening, or a change, has just made, and the first day it
    may use. Does nothing yet, so everything stays in the bank (ADR-013)."""
