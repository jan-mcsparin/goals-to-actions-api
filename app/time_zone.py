"""The phone sends its time zone name with every request, and "today" is worked out from it
here on the server (shared decision 9)."""

from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, Header, HTTPException


def today(x_time_zone: Annotated[str, Header()]) -> date:
    """Today where the phone is. Asked for only by routes that need the day."""
    try:
        zone = ZoneInfo(x_time_zone)
    except KeyError, ValueError, OSError:
        raise HTTPException(
            422, "X-Time-Zone must be a time zone name such as America/Denver."
        ) from None
    return datetime.now(zone).date()


Today = Annotated[date, Depends(today)]
