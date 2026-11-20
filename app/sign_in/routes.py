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


DeviceToken = Annotated[str | None, Depends(session_cookie)]


def signed_in(database: CurrentDatabase, token: str, old: str | None) -> Response:
    """A new session's cookie. The device's earlier session, if any, ends: it can't outlive
    the new one."""
    if old:
        end_session(database, old)
    response = Response(status_code=204)
    set_session_cookie(response, token)
    return response


@router.post("/code", responses=SIGN_IN_FAILED)
def redeem_code(body: RedeemCode, database: CurrentDatabase, moment: Moment) -> PasskeyOptions:
    """Spends a one-time code; returns the options for the browser to make a passkey."""
    options = rules.redeem_code(database, body.code, moment)
    return PasskeyOptions(challenge_id=options.challenge_id, options=options.options)


@router.post("/passkeys", status_code=204, responses=SIGN_IN_FAILED)
def add_passkey(
    body: SignedChallenge, database: CurrentDatabase, moment: Moment, old: DeviceToken
) -> Response:
    """Keeps the passkey made for a redeemed code, and signs this device in."""
    token = rules.add_passkey(database, body.challenge_id, body.credential, moment)
    return signed_in(database, token, old)


@router.post("/start")
def start_sign_in(database: CurrentDatabase, moment: Moment) -> PasskeyOptions:
    """The options for the browser to sign in with a passkey, and the challenge to send back."""
    options = rules.start_sign_in(database, moment)
    return PasskeyOptions(challenge_id=options.challenge_id, options=options.options)


@router.post("/finish", status_code=204, responses=SIGN_IN_FAILED)
def finish_sign_in(
    body: SignedChallenge, database: CurrentDatabase, moment: Moment, old: DeviceToken
) -> Response:
    """Checks the passkey's signature and signs this device in."""
    token = rules.finish_sign_in(database, body.challenge_id, body.credential, moment)
    return signed_in(database, token, old)


@router.post("/sign-out", status_code=204)
def sign_out(database: CurrentDatabase, token: DeviceToken) -> Response:
    """Ends this device's session on the server and clears its cookie. Without a live session
    there's nothing to end, and the answer is the same."""
    if token:
        end_session(database, token)
    response = Response(status_code=204)
    clear_session_cookie(response)
    return response
