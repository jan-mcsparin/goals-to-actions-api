from datetime import date

from app.turnover.due import ItemSchedule, ending, goal_slots, item_slots, last_week_of_period

MON = date(2026, 11, 16)
STARTS = date(2026, 11, 1)  # long before every case below


def sessions(count: int, week: date, first_day: date) -> list[int]:
    return [number for _, number in goal_slots(count, week, first_day)]


def test_a_goal_gets_its_full_target_when_it_starts_on_monday() -> None:
    assert goal_slots(3, MON, MON) == [(MON, 1), (MON, 2), (MON, 3)]


def test_a_goal_started_on_saturday_gets_two_sessions_of_three() -> None:
    assert sessions(3, MON, date(2026, 11, 21)) == [1, 2]


def test_a_goal_started_on_sunday_gets_one() -> None:
    assert sessions(3, MON, date(2026, 11, 22)) == [1]


def test_a_goal_that_starts_after_the_week_gets_none() -> None:
    assert goal_slots(3, MON, date(2026, 11, 23)) == []


def test_a_goal_that_started_earlier_gets_its_full_target() -> None:
    assert sessions(5, MON, date(2026, 10, 1)) == [1, 2, 3, 4, 5]


def weekly(weekday: int, starts_on: date = STARTS) -> ItemSchedule:
    return ItemSchedule("weekly", starts_on, weekday=weekday)


def test_a_weekly_item_is_due_once_a_week() -> None:
    assert item_slots(weekly(2), MON, MON) == [(MON, 1)]


def test_a_weekly_item_waits_for_its_first_matching_day() -> None:
    thursday_start = date(2026, 11, 19)
    assert item_slots(weekly(2, thursday_start), MON, MON) == []
    assert item_slots(weekly(4, thursday_start), MON, MON) == [(MON, 1)]
    assert item_slots(weekly(2, thursday_start), date(2026, 11, 23), MON) == [
        (date(2026, 11, 23), 1)
    ]


def monthly(day: int, starts_on: date = STARTS) -> ItemSchedule:
    return ItemSchedule("monthly", starts_on, day_of_month=day)


def test_a_monthly_item_is_due_in_the_week_its_day_falls_in() -> None:
    nov30 = date(2026, 11, 30)  # the week of Nov 30 holds Dec 1
    assert item_slots(monthly(1), nov30, nov30) == [(nov30, 1)]
    assert item_slots(monthly(1), date(2026, 11, 23), nov30) == []
    assert item_slots(monthly(28), date(2026, 11, 23), nov30) == [(date(2026, 11, 23), 1)]


def test_a_monthly_item_isnt_due_before_its_starts_on() -> None:
    week = date(2026, 11, 23)
    assert item_slots(monthly(28, date(2026, 11, 29)), week, week) == []


def flexible(times: int, period: str, starts_on: date = STARTS) -> ItemSchedule:
    return ItemSchedule("flexible", starts_on, times=times, period=period)  # type: ignore[arg-type]


def test_a_flexible_weekly_item_has_its_times() -> None:
    assert item_slots(flexible(3, "week"), MON, MON) == [(MON, 1), (MON, 2), (MON, 3)]


def test_a_flexible_item_added_on_saturday_is_capped_like_a_goal() -> None:
    assert item_slots(flexible(3, "week"), MON, date(2026, 11, 21)) == [(MON, 1), (MON, 2)]


def test_a_two_week_period_is_anchored_on_the_week_of_starts_on() -> None:
    item = flexible(1, "two_weeks", date(2026, 11, 18))  # anchor: Mon Nov 16
    assert item_slots(item, MON, MON) == [(MON, 1)]
    assert item_slots(item, date(2026, 11, 23), MON) == [(MON, 1)]  # same period, second week
    assert item_slots(item, date(2026, 11, 30), MON) == [(date(2026, 11, 30), 1)]
    assert item_slots(item, date(2026, 11, 9), MON) == []  # before it starts


def test_a_month_is_the_weeks_whose_monday_falls_in_it() -> None:
    item = flexible(1, "month")
    # November 2026 has five Mondays: 2, 9, 16, 23 and 30.
    for week in (date(2026, 11, 2), date(2026, 11, 23), date(2026, 11, 30)):
        assert item_slots(item, week, week) == [(date(2026, 11, 2), 1)]
    # December's first Monday is the 7th.
    assert item_slots(item, date(2026, 12, 7), MON) == [(date(2026, 12, 7), 1)]
    assert last_week_of_period(item, date(2026, 11, 2)) == date(2026, 11, 30)
    assert last_week_of_period(item, date(2026, 12, 7)) == date(2026, 12, 28)


def test_a_flexible_item_added_midmonth_has_that_months_task() -> None:
    item = flexible(1, "month", date(2026, 11, 19))
    assert item_slots(item, MON, MON) == [(date(2026, 11, 2), 1)]


def test_a_by_hand_task_and_a_fixed_day_task_roll_over() -> None:
    assert ending("by_hand", None, None, MON) == "rolls_over"
    assert ending("recurring_item", weekly(2), MON, MON) == "rolls_over"
    assert ending("recurring_item", monthly(1), MON, MON) == "rolls_over"


def test_a_weekly_target_session_lapses() -> None:
    assert ending("weekly_target", None, MON, MON) == "lapses"


def test_a_flexible_task_lapses_at_the_end_of_its_period_and_carries_inside_it() -> None:
    assert ending("recurring_item", flexible(3, "week"), MON, MON) == "lapses"

    two_weeks = flexible(1, "two_weeks", MON)
    assert ending("recurring_item", two_weeks, MON, MON) == "rolls_over"
    assert ending("recurring_item", two_weeks, MON, date(2026, 11, 23)) == "lapses"

    month = flexible(1, "month")
    start = date(2026, 11, 2)
    assert ending("recurring_item", month, start, date(2026, 11, 23)) == "rolls_over"
    assert ending("recurring_item", month, start, date(2026, 11, 30)) == "lapses"
