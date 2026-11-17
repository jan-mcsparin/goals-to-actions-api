"""Weeks start on Monday and are named by the date of their Monday."""

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
