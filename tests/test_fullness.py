"""The expected counts' pure rules: what opening a week would make (spec `any-week`)."""

from datetime import date, timedelta

from app.turnover.due import ItemSchedule, expected_item_tasks, expected_sessions

DEC_7 = date(2026, 12, 7)
STARTS = date(2026, 11, 17)


def test_a_goal_gets_its_full_target_in_a_later_week() -> None:
    assert expected_sessions(3, DEC_7, date(2026, 10, 1)) == 3


def test_a_goal_starting_on_saturday_gets_two_sessions() -> None:
    assert expected_sessions(3, DEC_7, date(2026, 12, 12)) == 2


def test_a_goal_starting_after_the_week_gets_none() -> None:
    assert expected_sessions(3, DEC_7, date(2026, 12, 14)) == 0


def test_a_weekly_item_makes_one_task() -> None:
    assert expected_item_tasks(ItemSchedule("weekly", STARTS, weekday=2), DEC_7) == 1


def test_a_monthly_item_makes_one_in_the_week_its_day_falls_in() -> None:
    rent = ItemSchedule("monthly", STARTS, day_of_month=10)
    assert [expected_item_tasks(rent, DEC_7 + timedelta(weeks=n)) for n in range(-1, 2)] == [
        0,
        1,
        0,
    ]


def test_a_weekly_flexible_item_makes_its_times() -> None:
    laundry = ItemSchedule("flexible", STARTS, times=2, period="week")
    assert expected_item_tasks(laundry, DEC_7) == 2


def test_a_two_week_item_counts_in_its_periods_first_week_only() -> None:
    bathroom = ItemSchedule("flexible", STARTS, times=1, period="two_weeks")
    # Periods start on 16 Nov, 30 Nov, 14 Dec.
    assert expected_item_tasks(bathroom, date(2026, 11, 30)) == 1
    assert expected_item_tasks(bathroom, DEC_7) == 0
    assert expected_item_tasks(bathroom, date(2026, 12, 14)) == 1


def test_a_monthly_flexible_item_counts_in_the_first_week_of_its_month() -> None:
    gutters = ItemSchedule("flexible", STARTS, times=2, period="month")
    # December's weeks start on 7 Dec (its first Monday), 14, 21 and 28.
    counts = [expected_item_tasks(gutters, DEC_7 + timedelta(weeks=n)) for n in range(4)]
    assert counts == [2, 0, 0, 0]


def test_a_flexible_item_starting_inside_a_period_counts_in_its_first_week() -> None:
    # Opening makes the month's tasks in the first week the item exists.
    gutters = ItemSchedule("flexible", date(2026, 12, 16), times=1, period="month")
    counts = [expected_item_tasks(gutters, DEC_7 + timedelta(weeks=n)) for n in range(4)]
    assert counts == [0, 1, 0, 0]


def test_an_item_starting_after_the_week_makes_none() -> None:
    later = ItemSchedule("weekly", date(2026, 12, 15), weekday=1)
    assert expected_item_tasks(later, DEC_7) == 0
