"""A write is refused unless it comes from the app's own origin (ADR-012). Browsers send
`Origin` on every write, same-origin included. Reads aren't checked: a page elsewhere can't
read the answer, and the phone may read before it can write."""

from fastapi import HTTPException, Request

from app.config import APP_ORIGIN

WRITES = {"POST", "PUT", "PATCH", "DELETE"}


def same_origin(request: Request) -> None:
    if request.method in WRITES and request.headers.get("origin") != APP_ORIGIN:
        raise HTTPException(status_code=403, detail="Not from the app")
