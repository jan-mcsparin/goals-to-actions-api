"""The sign-in routes (ADR-012). They answer without a session: they're how one starts. None
is queueable, and the passkey steps are one-shot on purpose: a code and a challenge work once."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response

from app.dependencies import CurrentDatabase
from app.schemas import ErrorMessage
from app.sign_in import rules
from app.sign_in.models import PasskeyOptions, RedeemCode, SignedChallenge
from app.sign_in.session import (
    clear_session_cookie,
    end_session,
    session_cookie,
    set_session_cookie,
)
from app.time_zone import clock

router = APIRouter(prefix="/sign-in", tags=["sign-in"])

Moment = Annotated[datetime, Depends(clock)]
SIGN_IN_FAILED: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorMessage, "description": "The code, challenge or passkey didn't work."}
}


@router.post("/code", responses=SIGN_IN_FAILED)
def redeem_code(body: RedeemCode, database: CurrentDatabase, moment: Moment) -> PasskeyOptions:
    """Spends a one-time code; returns the options for the browser to make a passkey."""
    options = rules.redeem_code(database, body.code, moment)
    return PasskeyOptions(challenge_id=options.challenge_id, options=options.options)


@router.post("/passkeys", status_code=204, responses=SIGN_IN_FAILED)
def add_passkey(body: SignedChallenge, database: CurrentDatabase, moment: Moment) -> Response:
    """Keeps the passkey made for a redeemed code, and signs this device in."""
    token = rules.add_passkey(database, body.challenge_id, body.credential, moment)
    response = Response(status_code=204)
    set_session_cookie(response, token)
    return response


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
