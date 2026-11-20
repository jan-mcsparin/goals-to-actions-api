"""The planner (ADR-008, ADR-013): places recurring work on days, and nothing else.

`place` is the rule, pure code with no database or clock (spec `planner`, "Where it puts
things"). `place_new_work` is the hook opening a week and every change call."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import Connection


@dataclass(frozen=True)
class Group:
    """The new tasks of one goal or item, to place together.

    `fixed_day` is a weekly or monthly item's day. `starts_on` is the goal's or item's start,
    which nothing goes before. `earlier_days` are where the group's other tasks this week
    already are (`None` for one in the bank): a group that has some takes the lightest day
    without one, rather than being spread."""

    task_ids: tuple[UUID, ...]
    fixed_day: date | None = None
    starts_on: date | None = None
    earlier_days: tuple[date | None, ...] = ()


@dataclass(frozen=True)
class Placement:
    task_id: UUID
    day: date


def place(
    week: date, first_day: date, load: Mapping[date, int], groups: Sequence[Group]
) -> list[Placement]:
    """Where each group's tasks go, in the given order: each group sees the days as the
    earlier ones left them. `load` is how many tasks each day already holds. The cap is not
    consulted. With no day left from `first_day`, a group stays in the bank."""
    counts = {week + timedelta(days=n): load.get(week + timedelta(days=n), 0) for n in range(7)}
    placed: list[Placement] = []
    for group in groups:
        start = max(first_day, group.starts_on or first_day)
        days = [day for day in counts if day >= start]
        if not days:
            continue
        for task_id, day in zip(group.task_ids, days_for(group, days, counts), strict=True):
            counts[day] += 1
            placed.append(Placement(task_id, day))
    return placed


def days_for(group: Group, days: list[date], counts: dict[date, int]) -> list[date]:
    count = len(group.task_ids)
    if group.fixed_day is not None:
        return [max(group.fixed_day, days[0])] * count
    if group.earlier_days:
        return beside(count, set(group.earlier_days), days, dict(counts))
    return spread(count, days, dict(counts))


def spread(count: int, days: list[date], counts: dict[date, int]) -> list[date]:
    """`count` tasks spaced evenly over `days`, `len(days) // count` apart, from the start
    whose days hold the fewest tasks (ties to the earlier). More tasks than days: one on
    each day, then the rest spread again."""
    if count > len(days):
        for day in days:
            counts[day] += 1
        return days + spread(count - len(days), days, counts)
    step = len(days) // count
    starts = range(len(days) - (count - 1) * step)
    best = min(starts, key=lambda s: (sum(counts[days[s + k * step]] for k in range(count)), s))
    return [days[best + k * step] for k in range(count)]


def beside(
    count: int, taken: set[date | None], days: list[date], counts: dict[date, int]
) -> list[date]:
    """Each task on the lightest day that holds none of the group's tasks (ties to the
    earlier), or the lightest day when every day does."""
    chosen: list[date] = []
    for _ in range(count):
        free = [day for day in days if day not in taken] or days
        day = min(free, key=lambda d: (counts[d], d))
        chosen.append(day)
        taken.add(day)
        counts[day] += 1
    return chosen


def place_new_work(
    connection: Connection, user_id: UUID, task_ids: list[UUID], first_day: date
) -> None:
    """Called with the tasks a week's opening, or a change, has just made, and the first day it
    may use. Does nothing yet, so everything stays in the bank (ADR-013)."""
