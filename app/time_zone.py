"""The phone sends its time zone name with every request, and "today" is worked out from it
here on the server (shared decision 9)."""

from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, Header
from fastapi.exceptions import RequestValidationError


def today(x_time_zone: Annotated[str, Header()]) -> date:
    """Today where the phone is. Asked for only by routes that need the day."""
    try:
        zone = ZoneInfo(x_time_zone)
    except KeyError, ValueError, OSError:
        # The shape FastAPI gives a missing header, so every 422 reads the same.
        raise RequestValidationError(
            [
                {
                    "type": "time_zone",
                    "loc": ("header", "x-time-zone"),
                    "msg": "Must be a time zone name such as America/Denver.",
                    "input": x_time_zone,
                }
            ]
        ) from None
    return datetime.now(zone).date()


Today = Annotated[date, Depends(today)]
