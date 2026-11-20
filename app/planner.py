"""The planner (ADR-008, ADR-013): places recurring work on days, and nothing else.

`place` is the rule, pure code with no database or clock (spec `planner`, "Where it puts
things"). `place_new_work` is the hook opening a week and every change call."""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID

from sqlalchemy import Connection

from app.db import planner


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
    """Places the recurring tasks a week's opening, or a change, has just made, from
    `first_day` on. Anything else it's handed (a task added by hand) stays in the bank."""
    if not task_ids:
        return
    queries = planner.Querier(connection)
    context = list(queries.list_placement_context(user_id=user_id, task_ids=task_ids))
    for week in sorted({row.week for row in context}):
        new = [row for row in context if row.week == week]
        new_ids = {row.task_id for row in new}
        others = [
            row
            for row in queries.list_week_places(user_id=user_id, week=week)
            if row.task_id not in new_ids
        ]
        load = Counter(row.planned_day for row in others if row.planned_day is not None)
        for placement in place(week, first_day, load, groups_of(new, others, week)):
            queries.place_generated_task(
                planner.PlaceGeneratedTaskParams(
                    day=placement.day,
                    task_id=placement.task_id,
                    user_id=user_id,
                    week=week,
                    first_day=first_day,
                )
            )


def groups_of(
    new: list[planner.ListPlacementContextRow],
    others: list[planner.ListWeekPlacesRow],
    week: date,
) -> list[Group]:
    """One group per goal or item, in the order that decides who sees the lighter days first
    (spec `planner`, "The order")."""
    by_owner: dict[UUID, list[planner.ListPlacementContextRow]] = {}
    for row in new:
        by_owner.setdefault(owner_of(row.goal_id, row.recurring_item_id), []).append(row)
    ordered = sorted(by_owner.items(), key=lambda entry: turn_of(entry[1][0], entry[0]))
    return [
        Group(
            task_ids=tuple(row.task_id for row in rows),
            fixed_day=fixed_day(rows[0].item_kind, rows[0].weekday, rows[0].day_of_month, week),
            starts_on=rows[0].starts_on,
            earlier_days=tuple(
                row.planned_day for row in others if (row.goal_id or row.recurring_item_id) == owner
            ),
        )
        for owner, rows in ordered
    ]


def owner_of(goal_id: UUID | None, item_id: UUID | None) -> UUID:
    owner = goal_id or item_id
    assert owner is not None
    return owner


def turn_of(
    row: planner.ListPlacementContextRow, owner: UUID
) -> tuple[int, int, int, datetime, str]:
    """Fixed-day tasks; then maintenance (flexible items with no aspiration); then work under
    an active aspiration, by its position, goals before items; then the rest."""
    is_item = int(row.recurring_item_id is not None)
    if row.item_kind in ("weekly", "monthly"):
        rank = 0
    elif is_item and row.item_aspiration_id is None:
        rank = 1
    elif row.aspiration_position is not None:
        rank = 2
    else:
        rank = 3
    return (rank, row.aspiration_position or 0, is_item, row.made_at, str(owner))


def fixed_day(
    kind: str | None, weekday: int | None, day_of_month: int | None, week: date
) -> date | None:
    """A weekly or monthly item's day in `week`, if it has one there."""
    if kind == "weekly" and weekday is not None:
        return week + timedelta(days=weekday - 1)
    if kind == "monthly":
        for offset in range(7):
            day = week + timedelta(days=offset)
            if day.day == day_of_month:
                return day
    return None
