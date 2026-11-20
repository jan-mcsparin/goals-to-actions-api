"""The sign-in routes (ADR-012). They answer without a session: they're how one starts."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.dependencies import CurrentDatabase
from app.sign_in.session import clear_session_cookie, end_session, session_cookie

router = APIRouter(prefix="/sign-in", tags=["sign-in"])


@router.post("/sign-out", status_code=204)
def sign_out(
    database: CurrentDatabase, token: Annotated[str | None, Depends(session_cookie)]
) -> Response:
    """Ends this device's session on the server and clears its cookie. Without a live session
    there's nothing to end, and the answer is the same."""
    if token:
        end_session(database, token)
    response = Response(status_code=204)
    clear_session_cookie(response)
    return response
