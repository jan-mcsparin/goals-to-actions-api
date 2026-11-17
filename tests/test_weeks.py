from datetime import date

from app.weeks import target_week, week_of

MONDAY = date(2026, 11, 16)
SUNDAY = date(2026, 11, 22)
NEXT_MONDAY = date(2026, 11, 23)


def test_a_week_is_named_by_its_monday() -> None:
    assert week_of(MONDAY) == MONDAY
    assert week_of(date(2026, 11, 19)) == MONDAY
    assert week_of(SUNDAY) == MONDAY


def test_a_target_change_takes_effect_this_week() -> None:
    assert target_week(date(2026, 11, 19), planned_through_week=None) == MONDAY
    assert target_week(date(2026, 11, 19), planned_through_week=MONDAY) == MONDAY


def test_once_next_week_is_open_a_target_change_takes_effect_from_it() -> None:
    assert target_week(SUNDAY, planned_through_week=NEXT_MONDAY) == NEXT_MONDAY
