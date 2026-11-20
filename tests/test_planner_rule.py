"""The placing rule, by example (spec `planner`, "Where it puts things"). Pure code."""

import random
from datetime import date, timedelta
from uuid import UUID

from app.planner import Group, place

MON = date(2026, 11, 16)
TUE, WED, THU, FRI, SAT, SUN = (MON + timedelta(days=n) for n in range(1, 7))
WEEK = [MON, TUE, WED, THU, FRI, SAT, SUN]


def ids(count: int, start: int = 1) -> tuple[UUID, ...]:
    return tuple(UUID(int=start + n) for n in range(count))


def days_of(group: Group, first_day: date = MON, load: dict[date, int] | None = None) -> list[date]:
    placed = place(MON, first_day, load or {}, [group])
    by_task = {placement.task_id: placement.day for placement in placed}
    return [by_task[task_id] for task_id in group.task_ids if task_id in by_task]


def test_three_sessions_over_a_whole_week_go_monday_wednesday_friday() -> None:
    assert days_of(Group(ids(3))) == [MON, WED, FRI]


def test_spreading_starts_where_the_chosen_days_are_lightest() -> None:
    assert days_of(Group(ids(3)), load={MON: 2}) == [TUE, THU, SAT]


def test_ties_between_starts_go_to_the_earlier_one() -> None:
    assert days_of(Group(ids(3)), load={MON: 1, TUE: 1, SUN: 1}) == [MON, WED, FRI]


def test_one_task_goes_on_the_lightest_day() -> None:
    load = {day: 1 for day in WEEK} | {THU: 0}
    assert days_of(Group(ids(1)), load=load) == [THU]


def test_a_week_first_opened_on_wednesday_spreads_from_wednesday() -> None:
    # 5 days, 2 tasks: 2 apart, so Wed–Fri, Thu–Sat or Fri–Sun.
    assert days_of(Group(ids(2)), first_day=WED) == [WED, FRI]


def test_six_over_seven_go_one_a_day() -> None:
    assert days_of(Group(ids(6))) == [MON, TUE, WED, THU, FRI, SAT]


def test_more_tasks_than_days_go_one_a_day_and_the_rest_spread_again() -> None:
    assert days_of(Group(ids(5)), first_day=SAT) == [SAT, SUN, SAT, SUN, SAT]


def test_more_tasks_than_days_spread_the_rest_over_the_lightest_days() -> None:
    placed = days_of(Group(ids(4)), first_day=FRI, load={FRI: 3})
    assert sorted(placed) == [FRI, SAT, SAT, SUN]


def test_a_fixed_day_task_goes_on_its_day() -> None:
    assert days_of(Group(ids(1), fixed_day=THU)) == [THU]


def test_a_fixed_day_task_goes_on_its_day_however_full() -> None:
    assert days_of(Group(ids(1), fixed_day=THU), load={THU: 9}) == [THU]


def test_a_fixed_day_task_whose_day_has_passed_goes_on_the_first_day() -> None:
    assert days_of(Group(ids(1), fixed_day=MON), first_day=THU) == [THU]


def test_nothing_is_placed_with_no_day_left() -> None:
    assert place(MON, MON + timedelta(days=7), {}, [Group(ids(3))]) == []
    assert place(MON, MON + timedelta(days=7), {}, [Group(ids(1), fixed_day=SUN)]) == []


def test_the_empty_week_places_nothing() -> None:
    assert place(MON, MON, {MON: 3}, []) == []


def test_a_group_that_starts_on_friday_is_spread_from_friday() -> None:
    # 3 days, 2 tasks: 1 apart.
    assert days_of(Group(ids(2), starts_on=FRI)) == [FRI, SAT]


def test_new_work_for_a_group_with_tasks_goes_on_the_lightest_day_without_one() -> None:
    group = Group(ids(1), earlier_days=(MON, WED, FRI))
    assert days_of(group, first_day=THU, load={MON: 1, WED: 1, FRI: 1, THU: 2, SAT: 1}) == [SUN]


def test_new_work_for_a_group_with_tasks_takes_the_earlier_day_on_a_tie() -> None:
    group = Group(ids(2), earlier_days=(TUE,))
    assert days_of(group, first_day=WED, load={TUE: 1}) == [WED, THU]


def test_new_work_for_a_group_with_tasks_only_in_the_bank_goes_on_the_lightest_day() -> None:
    group = Group(ids(1), earlier_days=(None,))
    assert days_of(group, first_day=WED, load={WED: 2, THU: 1, FRI: 1}) == [SAT]


def test_when_every_day_left_holds_the_group_it_takes_the_lightest_day() -> None:
    group = Group(ids(1), earlier_days=(SAT, SUN))
    assert days_of(group, first_day=SAT, load={SAT: 3, SUN: 1}) == [SUN]


def test_two_goals_compete_for_the_lighter_days_in_order() -> None:
    first, second = Group(ids(3, 1)), Group(ids(3, 10))
    placed = {p.task_id: p.day for p in place(MON, MON, {}, [first, second])}
    assert [placed[i] for i in first.task_ids] == [MON, WED, FRI]
    assert [placed[i] for i in second.task_ids] == [TUE, THU, SAT]


def test_a_day_over_the_cap_still_takes_a_spread_task_when_it_is_lightest() -> None:
    load = {day: 9 for day in WEEK}
    assert days_of(Group(ids(1)), load=load) == [MON]


def random_groups(rng: random.Random) -> list[Group]:
    groups: list[Group] = []
    start = 1
    for _ in range(rng.randint(0, 5)):
        count = rng.randint(1, 9)
        fixed = rng.choice([None, *WEEK]) if count == 1 else None
        earlier = tuple(rng.choice([None, *WEEK]) for _ in range(rng.randint(0, 3)))
        starts = rng.choice([None, *WEEK, SUN + timedelta(days=3)])
        groups.append(Group(ids(count, start), fixed, starts, earlier))
        start += 100
    return groups


def test_properties_hold_for_many_weeks() -> None:
    rng = random.Random(10)
    for _ in range(500):
        groups = random_groups(rng)
        first_day = MON + timedelta(days=rng.randint(-3, 8))
        load = {day: rng.randint(0, 6) for day in WEEK}
        placed = place(MON, first_day, load, groups)
        given = {task_id for group in groups for task_id in group.task_ids}
        assert {p.task_id for p in placed} <= given
        assert len({p.task_id for p in placed}) == len(placed)
        for p in placed:
            assert MON <= p.day <= SUN
            assert p.day >= first_day
        for group in groups:
            for p in placed:
                if p.task_id in group.task_ids and group.starts_on is not None:
                    assert p.day >= group.starts_on
        assert place(MON, first_day, dict(load), list(groups)) == placed


def test_every_task_is_placed_while_a_day_is_left() -> None:
    rng = random.Random(11)
    for _ in range(200):
        groups = [g for g in random_groups(rng) if g.starts_on is None]
        placed = place(MON, WED, {}, groups)
        assert len(placed) == sum(len(group.task_ids) for group in groups)
