"""The phone sends its time zone name with every request, and "today" is worked out from it
here on the server (shared decision 9). The moment itself comes from `clock`, which tests
replace so no test reads the real date."""

from datetime import UTC, date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, Header
from fastapi.exceptions import RequestValidationError


def clock() -> datetime:
    """The real moment, in UTC. The one thing tests override."""
    return datetime.now(UTC)


def zone_of(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except KeyError, ValueError, OSError:
        # The shape FastAPI gives a missing header, so every 422 reads the same.
        raise RequestValidationError(
            [
                {
                    "type": "time_zone",
                    "loc": ("header", "x-time-zone"),
                    "msg": "Must be a time zone name such as America/Denver.",
                    "input": name,
                }
            ]
        ) from None


def now(
    x_time_zone: Annotated[str, Header()], moment: Annotated[datetime, Depends(clock)]
) -> datetime:
    """The moment where the phone is. Asked for only by routes that need the day."""
    return moment.astimezone(zone_of(x_time_zone))


def today(moment: Annotated[datetime, Depends(now)]) -> date:
    return moment.date()


Now = Annotated[datetime, Depends(now)]
Today = Annotated[date, Depends(today)]
