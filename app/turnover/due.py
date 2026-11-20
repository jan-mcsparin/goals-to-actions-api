"""What a week is due, and how an unfinished task ends. Pure code: no database, no clock.

A generated task is named by `(period_start, number)`: the Monday of its week or period,
and which of that period's tasks it is (session 2 of 3). The pair is unique per goal or
item, so a week can't be filled twice. Callers read what exists first and make only the
pairs that are missing."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from app.weeks import week_of

Slot = tuple[date, int]
Ending = Literal["rolls_over", "lapses"]


@dataclass(frozen=True)
class ItemSchedule:
    """A recurring item's schedule, as the table keeps it. Weekdays run 1 (Monday) to 7."""

    kind: Literal["weekly", "monthly", "flexible"]
    starts_on: date
    weekday: int | None = None
    day_of_month: int | None = None
    times: int | None = None
    period: Literal["week", "two_weeks", "month"] | None = None


def days_left(week: date, first_day: date) -> int:
    """How many days of the week are usable from `first_day`: all seven if it's on or
    before Monday, none if it's after the week."""
    return max(0, min(7, (week + timedelta(days=7) - first_day).days))


def goal_slots(sessions: int, week: date, first_day: date) -> list[Slot]:
    """A goal's sessions for a week. In the week it starts, or comes back midweek, at most one
    per day left, today included. `first_day` is the later of its start date and today."""
    return [(week, number) for number in range(1, min(sessions, days_left(week, first_day)) + 1)]


def item_slots(item: ItemSchedule, week: date, first_day: date) -> list[Slot]:
    """The tasks an item has in the period that `week` is in, or none if it isn't due.
    A flexible item's period task is the same for each week of the period, so a caller
    that skips what exists makes it once."""
    if item.kind in ("weekly", "monthly"):
        day = fixed_day(item.kind, item.weekday, item.day_of_month, week)
        return [(week, 1)] if day is not None and day >= item.starts_on else []
    assert item.times is not None and item.period is not None
    if week < week_of(item.starts_on):
        return []
    start = period_start(item, week)
    if item.period == "week":
        count = min(item.times, days_left(week, first_day))
    else:
        count = item.times
    return [(start, number) for number in range(1, count + 1)]


def fixed_day(
    kind: str | None, weekday: int | None, day_of_month: int | None, week: date
) -> date | None:
    """A weekly or monthly item's day in `week`, or `None` if it has none there (a monthly
    item's day falls in one week of the month)."""
    if kind == "weekly" and weekday is not None:
        return week + timedelta(days=weekday - 1)
    if kind == "monthly":
        for offset in range(7):
            day = week + timedelta(days=offset)
            if day.day == day_of_month:
                return day
    return None


def period_start(item: ItemSchedule, week: date) -> date:
    """The Monday that starts the flexible period `week` is in. A two-week period is
    anchored on the week of `starts_on`; a month is the weeks whose Monday falls in it."""
    if item.period == "two_weeks":
        anchor = week_of(item.starts_on)
        return anchor + timedelta(days=14 * ((week - anchor).days // 14))
    if item.period == "month":
        first = week.replace(day=1)
        return first + timedelta(days=(7 - first.weekday()) % 7)
    return week


def last_week_of_period(item: ItemSchedule, start: date) -> date:
    """The Monday of the last week of the period that starts on `start`."""
    if item.period == "two_weeks":
        return start + timedelta(weeks=1)
    if item.period == "month":
        week = start
        while (week + timedelta(weeks=1)).month == start.month:
            week += timedelta(weeks=1)
        return week
    return start


def ending(
    origin: str, item: ItemSchedule | None, period_start_: date | None, week: date
) -> Ending:
    """What closing `week` does to a task that is still unfinished (data model, "How a week
    ends"). A task added by hand and a fixed-day recurring task roll over; a weekly target's
    session lapses; a flexible item's task lapses at the end of its period and rolls over
    inside it."""
    if origin == "weekly_target":
        return "lapses"
    if origin == "recurring_item":
        assert item is not None and period_start_ is not None
        if item.kind == "flexible":
            return "lapses" if week >= last_week_of_period(item, period_start_) else "rolls_over"
    return "rolls_over"
