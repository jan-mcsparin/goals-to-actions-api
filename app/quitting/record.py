"""A quitting goal's record: what the writes return, and what the goal's page and the week
read show. Worked out on every read; nothing here is stored."""

from datetime import date
from uuid import UUID

from sqlalchemy import Connection

from app.db import quit_days, urge_ratings
from app.quitting.models import QuitDay


def quit_day(connection: Connection, user_id: UUID, goal_id: UUID, day: date) -> QuitDay:
    held = {
        row.day: row.held
        for row in quit_days.Querier(connection).list_quit_days(
            user_id=user_id, goal_ids=[goal_id], from_day=day, through_day=day
        )
    }
    urges = {
        row.rated_on: row.level
        for row in urge_ratings.Querier(connection).list_urge_ratings(
            user_id=user_id, goal_ids=[goal_id], from_day=day, through_day=day
        )
    }
    return QuitDay(goal_id=goal_id, day=day, held=held.get(day), urge=urges.get(day))
