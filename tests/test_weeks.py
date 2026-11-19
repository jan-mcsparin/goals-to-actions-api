from datetime import date

from app.weeks import open_weeks, target_week, week_of

MONDAY = date(2026, 11, 16)
SUNDAY = date(2026, 11, 22)
NEXT_MONDAY = date(2026, 11, 23)
WEDNESDAY = date(2026, 11, 18)


def test_a_week_is_named_by_its_monday() -> None:
    assert week_of(MONDAY) == MONDAY
    assert week_of(date(2026, 11, 19)) == MONDAY
    assert week_of(SUNDAY) == MONDAY


def test_a_target_change_takes_effect_this_week() -> None:
    assert target_week(date(2026, 11, 19), None, None) == MONDAY
    assert target_week(date(2026, 11, 19), MONDAY, None) == MONDAY


def test_once_next_week_is_open_a_target_change_takes_effect_from_it() -> None:
    assert target_week(SUNDAY, NEXT_MONDAY, None) == NEXT_MONDAY


def test_after_a_wrap_up_on_sunday_night_the_current_week_is_next_week() -> None:
    weeks = open_weeks(SUNDAY, NEXT_MONDAY, MONDAY)

    assert weeks.current == NEXT_MONDAY
    assert not weeks.next_open
    assert target_week(SUNDAY, NEXT_MONDAY, MONDAY) == NEXT_MONDAY


def test_a_flight_west_doesnt_take_the_current_week_back() -> None:
    # The phone says Sunday again, but the week has been wrapped up.
    assert open_weeks(SUNDAY, NEXT_MONDAY, MONDAY).current == NEXT_MONDAY


def test_a_closed_week_in_the_past_changes_nothing() -> None:
    weeks = open_weeks(WEDNESDAY, None, date(2026, 11, 9))

    assert weeks.current == MONDAY
