"""A quitting goal's daily answers and urge ratings. Each write runs inside the caller's
transaction and touches one row."""

from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import Connection

from app.db import goals, quit_days
from app.errors import NotAllowed, NotFound


def check_day(connection: Connection, user_id: UUID, goal_id: UUID, day: date, today: date) -> None:
    """Any day from the goal's start to today, so an answer queued offline still lands days
    later. The goal's status doesn't matter: the record is history."""
    goal = goals.Querier(connection).get_goal(id=goal_id, user_id=user_id)
    if goal is None:
        raise NotFound
    if goal.type != "quitting":
        raise NotAllowed("Only a quitting goal has a daily record.")
    if day < goal.start_date:
        raise NotAllowed("That day is before the goal started.")
    if day > today:
        raise NotAllowed("That day hasn't come yet.")


def answer(
    connection: Connection, user_id: UUID, goal_id: UUID, day: date, held: bool, today: date
) -> None:
    check_day(connection, user_id, goal_id, day, today)
    quit_days.Querier(connection).answer_quit_day(
        quit_days.AnswerQuitDayParams(
            id=uuid4(), user_id=user_id, goal_id=goal_id, day=day, held=held
        )
    )


def clear(connection: Connection, user_id: UUID, goal_id: UUID, day: date, today: date) -> None:
    check_day(connection, user_id, goal_id, day, today)
    quit_days.Querier(connection).clear_quit_day(goal_id=goal_id, user_id=user_id, day=day)
