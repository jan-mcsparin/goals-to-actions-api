"""Reworking one open week's tasks of a recurring item whose schedule changed (spec
`recurring-edit`). Pure code: no database, no clock.

The week's own tasks count towards what the new schedule is due there and take its slots;
extra open ones the app placed are removed, missing slots are made, and a fixed-day task moves
to its new day from today on. A carry-over from an earlier week is left alone."""

from collections.abc import Set
from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from app.turnover.due import Slot


@dataclass(frozen=True)
class WeekTask:
    """One of the item's tasks with a row in the week, done or open."""

    task_id: UUID
    slot: Slot
    day: date | None
    done: bool
    by_hand: bool
    own: bool  # False for a carry-over from an earlier week


@dataclass(frozen=True)
class Rework:
    keys: dict[UUID, Slot] = field(default_factory=dict)  # only the tasks whose key changes
    moves: dict[UUID, date] = field(default_factory=dict)
    remove: list[UUID] = field(default_factory=list)
    make: list[Slot] = field(default_factory=list)


def rework(
    week_tasks: list[WeekTask],
    wanted: list[Slot],
    fixed_day: date | None,
    today: date,
    taken: Set[Slot] = frozenset(),
) -> Rework:
    """`wanted` is the new schedule's slots for the week, counted from its Monday; `fixed_day`
    its day in the week, if it has one; `taken` every key the item's other tasks hold, deleted
    ones included."""
    own = sorted((t for t in week_tasks if t.own), key=keep_order)
    blocked = (set(taken) | {t.slot for t in week_tasks if not t.own}) - {t.slot for t in own}
    free = [slot for slot in wanted if slot not in blocked]
    staying, removed = split(own, len(free))

    keys: dict[UUID, Slot] = {}
    holders = {t.slot: t for t in staying if t.slot in free}
    open_slots = [slot for slot in free if slot not in holders]
    in_use = set(taken) | {t.slot for t in week_tasks} | set(wanted)
    past = max((number for _, number in in_use), default=0)
    for t in staying:
        if t.slot in holders and holders[t.slot] is t:
            continue
        if open_slots:
            keys[t.task_id] = open_slots.pop(0)
        else:
            past += 1
            keys[t.task_id] = (t.slot[0], past)
    for t in removed:
        past += 1
        keys[t.task_id] = (t.slot[0], past)

    moves = {
        t.task_id: fixed_day
        for t in staying
        if fixed_day is not None
        and fixed_day >= today
        and not t.done
        and not t.by_hand
        and t.day != fixed_day
    }
    return Rework(keys, moves, [t.task_id for t in removed], open_slots)


def keep_order(t: WeekTask) -> tuple[int, int]:
    """Who counts first: done, then placed by hand, then on a day (earliest first), then the
    bank. Removing goes the other way: the bank first, then the latest day."""
    if t.done:
        return (0, 0)
    if t.by_hand:
        return (1, 0)
    if t.day is not None:
        return (2, t.day.toordinal())
    return (3, 0)


def split(own: list[WeekTask], count: int) -> tuple[list[WeekTask], list[WeekTask]]:
    """The tasks that stay, and the open ones the app placed that are extra. Done and
    hand-placed tasks always stay, even past the count."""
    staying = own[:count]
    removed: list[WeekTask] = []
    for t in own[count:]:
        (staying if t.done or t.by_hand else removed).append(t)
    removed.reverse()
    return staying, removed
