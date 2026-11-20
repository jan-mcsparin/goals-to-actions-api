"""A quitting goal's record: what the writes return, and what the goal's page and the week
read show. Worked out on every read; nothing here is stored."""

from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import Connection

from app.db import models, quit_days, urge_ratings
from app.quitting.models import QuitDay, QuitRecord

# How far back the goal's page shows its days.
RECENT_DAYS = 28


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


@dataclass(frozen=True)
class Run:
    held: int
    unknown: int


def run_of(answers: dict[date, bool], start: date, today: date) -> Run:
    """Held answers since the last no (or the start), and the days before today since then
    with no answer. An unknown day neither ends the run nor adds to it."""
    noes = [day for day, held in answers.items() if not held]
    first = max(noes) + timedelta(days=1) if noes else start
    held = sum(held and day >= first for day, held in answers.items())
    past = [first + timedelta(days=n) for n in range(max(0, (today - first).days))]
    return Run(held=held, unknown=sum(day not in answers for day in past))


def quit_record(
    connection: Connection, user_id: UUID, goal: models.Goal, today: date
) -> QuitRecord:
    answers = {
        row.day: row.held
        for row in quit_days.Querier(connection).list_quit_days(
            user_id=user_id, goal_ids=[goal.id], from_day=goal.start_date, through_day=today
        )
    }
    first = max(goal.start_date, today - timedelta(days=RECENT_DAYS - 1))
    urges = {
        row.rated_on: row.level
        for row in urge_ratings.Querier(connection).list_urge_ratings(
            user_id=user_id, goal_ids=[goal.id], from_day=first, through_day=today
        )
    }
    days = [today - timedelta(days=n) for n in range((today - first).days + 1)]
    run = run_of(answers, goal.start_date, today)
    return QuitRecord(
        days=[
            QuitDay(goal_id=goal.id, day=day, held=answers.get(day), urge=urges.get(day))
            for day in days
        ],
        held_run=run.held,
        unknown_in_run=run.unknown,
    )
