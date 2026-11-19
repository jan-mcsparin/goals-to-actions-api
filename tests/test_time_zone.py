from datetime import UTC, datetime

import pytest
from fastapi.exceptions import RequestValidationError

from app.time_zone import now, today

MOMENT = datetime(2026, 11, 18, 19, 0, tzinfo=UTC)


def test_the_moment_is_in_the_time_zone_sent() -> None:
    assert now("America/Denver", MOMENT).hour == 12
    assert today(now("Pacific/Kiritimati", MOMENT)).isoformat() == "2026-11-19"


def test_today_differs_across_the_date_line() -> None:
    # 25 hours apart, so never the same day.
    assert today(now("Pacific/Kiritimati", MOMENT)) > today(now("Pacific/Pago_Pago", MOMENT))


@pytest.mark.parametrize("name", ["Mars/Olympus_Mons", "", "America", "../etc/passwd", "+07:00"])
def test_an_unknown_time_zone_is_refused(name: str) -> None:
    with pytest.raises(RequestValidationError) as refused:
        now(name, MOMENT)

    [error] = refused.value.errors()
    assert error["loc"] == ("header", "x-time-zone")
