"""Weeks start on Monday and are named by the date of their Monday."""

from dataclasses import dataclass
from datetime import date, timedelta


def week_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def target_week(today: date, planned_through_week: date | None) -> date:
    """The week a change to a weekly target takes effect: this week, or next week once next
    week is open (ADR-009), so Sunday night's score doesn't move.

    `week-turnover` finishes this: after a wrap-up the current week is the one after
    `closed_through_week`, which isn't stored yet."""
    this_week = week_of(today)
    if planned_through_week is not None and planned_through_week > this_week:
        return this_week + timedelta(weeks=1)
    return this_week


@dataclass(frozen=True)
class OpenWeeks:
    """The weeks a task can be in play: the current one and, from Sunday evening, the next."""

    current: date
    next_open: bool

    @property
    def next(self) -> date:
        return self.current + timedelta(weeks=1)

    def __contains__(self, week: object) -> bool:
        return week == self.current or (self.next_open and week == self.next)


def open_weeks(today: date, planned_through_week: date | None) -> OpenWeeks:
    """The current week is the phone's week. `week-turnover` makes it the week after
    `closed_through_week` when that's later, so it never goes backwards."""
    current = week_of(today)
    return OpenWeeks(current, planned_through_week is not None and planned_through_week > current)
