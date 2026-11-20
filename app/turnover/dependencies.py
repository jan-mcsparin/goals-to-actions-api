"""`Today`, the day every route that needs one asks for. Asking for it brings the weeks up to
date first: opening the app sends several requests at once, and the first one to arrive after
a week is due does the work, in its own write transaction (spec `week-turnover`). It also
keeps the phone's time zone on the user (spec `settings-sync`)."""

from datetime import date
from typing import Annotated

from fastapi import Depends

from app.db import users
from app.dependencies import CurrentDatabase, CurrentUserId
from app.time_zone import Now
from app.turnover.rules import catch_up, what_is_due


def today(database: CurrentDatabase, user_id: CurrentUserId, now: Now) -> date:
    """Today where the phone is, with the weeks brought up to date and the phone's time zone
    kept as last known. Reads first, so a request with nothing new writes nothing."""
    with database.read() as connection:
        owner = users.Querier(connection).get_user(id=user_id)
    zone = str(now.tzinfo)
    if owner is not None and owner.time_zone != zone:
        with database.transaction(user_id, "set time zone") as connection:
            users.Querier(connection).set_time_zone(id=user_id, time_zone=zone)
    if owner is not None and what_is_due(owner, now):
        with database.transaction(user_id, "close week") as connection:
            catch_up(connection, user_id, now)
    return now.date()


Today = Annotated[date, Depends(today)]
