"""Reworking one week's tasks of an edited recurring item, by example (spec `recurring-edit`).
Pure code."""

from datetime import date, timedelta
from uuid import UUID

from app.turnover.rework import WeekTask, rework

MON = date(2026, 11, 16)
TUE, WED, THU, FRI, SAT, SUN = (MON + timedelta(days=n) for n in range(1, 7))
LAST_MON = MON - timedelta(weeks=1)
TODAY = WED


def task(
    n: int,
    *,
    day: date | None = None,
    done: bool = False,
    by_hand: bool = False,
    own: bool = True,
    slot: tuple[date, int] | None = None,
) -> WeekTask:
    return WeekTask(
        task_id=UUID(int=n),
        slot=slot or (MON, n),
        day=day,
        done=done,
        by_hand=by_hand,
        own=own,
    )


def slots(count: int, start: date = MON) -> list[tuple[date, int]]:
    return [(start, n) for n in range(1, count + 1)]


# Moves


def test_a_fixed_day_task_moves_to_its_new_day_later_in_the_week() -> None:
    result = rework([task(1, day=THU)], slots(1), FRI, TODAY)

    assert result.moves == {UUID(int=1): FRI}


def test_a_task_whose_new_day_has_passed_stays() -> None:
    result = rework([task(1, day=THU)], slots(1), MON, TODAY)

    assert result.moves == {}


def test_a_task_whose_old_day_passed_moves_when_its_new_day_is_ahead() -> None:
    assert rework([task(1, day=MON)], slots(1), FRI, TODAY).moves == {UUID(int=1): FRI}


def test_a_task_can_move_onto_today() -> None:
    assert rework([task(1, day=THU)], slots(1), WED, TODAY).moves == {UUID(int=1): WED}


def test_a_task_in_the_bank_goes_on_its_new_day() -> None:
    assert rework([task(1)], slots(1), FRI, TODAY).moves == {UUID(int=1): FRI}


def test_a_done_task_never_moves() -> None:
    assert rework([task(1, day=MON, done=True)], slots(1), FRI, TODAY).moves == {}


def test_a_task_placed_by_hand_never_moves() -> None:
    assert rework([task(1, day=SAT, by_hand=True)], slots(1), FRI, TODAY).moves == {}


def test_a_task_already_on_its_day_isnt_moved() -> None:
    assert rework([task(1, day=FRI)], slots(1), FRI, TODAY).moves == {}


def test_a_carry_over_is_left_alone() -> None:
    carried = task(1, own=False, slot=(LAST_MON, 1))

    result = rework([carried], slots(1), FRI, TODAY)

    assert (result.moves, result.remove, result.keys) == ({}, [], {})
    assert result.make == [(MON, 1)]


def test_flexible_tasks_dont_move() -> None:
    assert rework([task(1, day=THU)], slots(3), None, TODAY).moves == {}


# Counts


def test_raising_the_count_makes_the_missing_ones() -> None:
    result = rework([task(1, day=MON), task(2, day=THU)], slots(3), None, TODAY)

    assert (result.make, result.remove) == ([(MON, 3)], [])


def test_lowering_the_count_removes_from_the_bank_first_then_the_latest_day() -> None:
    week = [task(1, day=MON, done=True), task(2, day=FRI), task(3), task(4, day=THU)]

    result = rework(week, slots(2), None, TODAY)

    assert result.remove == [UUID(int=3), UUID(int=2)]
    assert result.make == []


def test_done_and_hand_placed_tasks_are_never_removed() -> None:
    week = [task(1, day=MON, done=True), task(2, day=SAT, by_hand=True), task(3, day=THU)]

    result = rework(week, slots(1), None, TODAY)

    assert result.remove == [UUID(int=3)]


def test_not_due_this_week_removes_the_open_task_and_keeps_a_done_one() -> None:
    assert rework([task(1, day=THU)], [], None, TODAY).remove == [UUID(int=1)]
    assert rework([task(1, day=MON, done=True)], [], None, TODAY).remove == []


def test_nothing_changes_when_the_week_already_matches() -> None:
    week = [task(1, day=MON), task(2, day=THU)]

    result = rework(week, slots(2), None, TODAY)

    assert (result.keys, result.moves, result.remove, result.make) == ({}, {}, [], [])


# Keys


def test_survivors_take_the_new_periods_slots() -> None:
    month = date(2026, 11, 2)

    result = rework([task(1, day=THU)], slots(1, month), None, TODAY)

    assert result.keys == {UUID(int=1): (month, 1)}
    assert result.make == []


def test_a_done_task_counts_before_an_open_one() -> None:
    week = [task(1, day=THU), task(2, day=MON, done=True)]

    result = rework(week, slots(1), None, TODAY)

    assert result.remove == [UUID(int=1)]
    assert result.keys[UUID(int=2)] == (MON, 1)


def test_removed_and_surplus_tasks_get_numbers_past_any_in_use() -> None:
    week = [task(1, day=MON, done=True), task(2, day=TUE, done=True), task(3, day=THU)]

    result = rework(week, slots(1), None, TODAY, taken={(MON, 7)})

    assert UUID(int=1) not in result.keys  # already on the new slot
    assert sorted(result.keys[UUID(int=n)][1] for n in (2, 3)) == [8, 9]


def test_no_two_tasks_end_on_one_slot() -> None:
    week = [task(1, day=MON, slot=(MON, 3)), task(2, day=THU, slot=(MON, 1)), task(3)]

    result = rework(week, slots(2), None, TODAY)

    final = {t.task_id: result.keys.get(t.task_id, t.slot) for t in week}
    assert len(set(final.values())) == 3
    assert {final[UUID(int=1)], final[UUID(int=2)]} == {(MON, 1), (MON, 2)}


def test_a_slot_held_by_a_deleted_task_isnt_made_again() -> None:
    result = rework([], slots(2), None, TODAY, taken={(MON, 2)})

    assert result.make == [(MON, 1)]
