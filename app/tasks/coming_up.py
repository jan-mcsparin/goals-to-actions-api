"""The next 12 weeks in one read (spec `coming-up`): each week's counts, as the week read
gives them, and what's dated in it. Each part is read once for the whole range."""

from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import Connection

from app.db import tasks, users
from app.tasks import dated, fullness
from app.tasks.models import ComingUp, ComingUpWeek, Task, WeekCounts
from app.weeks import OpenWeeks, open_weeks, week_of


def coming_up(connection: Connection, user_id: UUID, today: date) -> ComingUp:
    owner = users.Querier(connection).get_user(id=user_id)
    assert owner is not None
    weeks = open_weeks(today, owner.planned_through_week, owner.closed_through_week)
    first, last = weeks.coming_up[0], weeks.coming_up[-1]
    dated_tasks = by_week(
        tasks.Querier(connection).list_dated_tasks(
            user_id=user_id, from_day=first, through_day=last + timedelta(days=6)
        ),
        lambda row: row.day,
    )
    check_ins = by_week(dated.check_ins(connection, user_id, first, last), lambda c: c.day)
    deadlines = by_week(dated.deadlines(connection, user_id, first, last), lambda d: d.day)
    expecting = fullness.expecting(connection, user_id, first, last)
    return ComingUp(
        weeks=[
            ComingUpWeek(
                week=week,
                status="open" if week in weeks else "notOpen",
                counts=counts(connection, user_id, week, weeks, expecting),
                tasks=[Task.from_row(row) for row in dated_tasks[week]],
                check_ins=check_ins[week],
                deadlines=deadlines[week],
            )
            for week in weeks.coming_up
        ]
    )


def counts(
    connection: Connection,
    user_id: UUID,
    week: date,
    weeks: OpenWeeks,
    expecting: fullness.Expecting,
) -> WeekCounts:
    """As `getWeek` counts: actual once the week is open, expected before."""
    if week in weeks:
        rows = tasks.Querier(connection).list_week_tasks(user_id=user_id, week=week)
        return fullness.actual(rows)
    return fullness.expected_counts(week, expecting)


def by_week[T](found: Iterable[T], day: Callable[[T], date]) -> defaultdict[date, list[T]]:
    grouped: defaultdict[date, list[T]] = defaultdict(list)
    for thing in found:
        grouped[week_of(day(thing))].append(thing)
    return grouped
