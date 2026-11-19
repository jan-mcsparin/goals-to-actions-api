"""Weeks start on Monday and are named by the date of their Monday."""

from dataclasses import dataclass
from datetime import date, timedelta


def week_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def current_week(today: date, closed_through_week: date | None) -> date:
    """The phone's week, or the week after the last one closed when that's later: after a
    wrap-up on Sunday night the current week is next week, and a flight west doesn't take
    it back."""
    this_week = week_of(today)
    if closed_through_week is not None:
        return max(this_week, closed_through_week + timedelta(weeks=1))
    return this_week


def target_week(
    today: date, planned_through_week: date | None, closed_through_week: date | None
) -> date:
    """The week a change to a weekly target takes effect: the current week, or next week
    once next week is open (ADR-009), so Sunday night's score doesn't move."""
    current = current_week(today, closed_through_week)
    if planned_through_week is not None and planned_through_week > current:
        return current + timedelta(weeks=1)
    return current


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


def open_weeks(
    today: date, planned_through_week: date | None, closed_through_week: date | None
) -> OpenWeeks:
    current = current_week(today, closed_through_week)
    return OpenWeeks(current, planned_through_week is not None and planned_through_week > current)
