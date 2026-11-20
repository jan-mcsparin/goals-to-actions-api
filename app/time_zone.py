"""The phone sends its time zone name with every request, and "today" is worked out from it
here on the server (shared decision 9). The moment itself comes from `clock`, which tests
replace so no test reads the real date."""

from datetime import UTC, datetime
from functools import cache
from typing import Annotated
from zoneinfo import ZoneInfo, available_timezones

from fastapi import Depends, Header
from fastapi.exceptions import RequestValidationError


def clock() -> datetime:
    """The real moment, in UTC. The one thing tests override."""
    return datetime.now(UTC)


@cache
def known_zones() -> frozenset[str]:
    """Every zone name, spelled exactly. Read once: listing them walks the zone files."""
    return frozenset(available_timezones())


def zone_of(name: str) -> ZoneInfo:
    try:
        # Checked against the list first: a case-insensitive file system (macOS) would load
        # "america/denver", which a Linux host refuses, and the name is kept on the user.
        if name not in known_zones():
            raise KeyError(name)
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


Now = Annotated[datetime, Depends(now)]
