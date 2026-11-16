from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.exceptions import RequestValidationError

from app.time_zone import today


def test_today_is_the_day_in_the_time_zone_sent() -> None:
    assert today("Pacific/Kiritimati") == datetime.now(ZoneInfo("Pacific/Kiritimati")).date()


def test_today_differs_across_the_date_line() -> None:
    # 25 hours apart, so never the same day.
    assert today("Pacific/Kiritimati") > today("Pacific/Pago_Pago")


@pytest.mark.parametrize("name", ["Mars/Olympus_Mons", "", "America", "../etc/passwd", "+07:00"])
def test_an_unknown_time_zone_is_refused(name: str) -> None:
    with pytest.raises(RequestValidationError) as refused:
        today(name)

    [error] = refused.value.errors()
    assert error["loc"] == ("header", "x-time-zone")
