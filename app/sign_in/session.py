"""Staying signed in (ADR-012): a session row holding the SHA-256 of a random token, and the
token in a `__Host-` cookie no page script can read. A session lasts 90 days from its last use;
last use is written at most once a day, in a small write of its own."""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException, Response
from fastapi.security import APIKeyCookie
from sqlalchemy import Connection

from app.database import Database, get_database
from app.db import sessions
from app.time_zone import clock

# `__Host-`: sent only to this host over HTTPS, never set by a sibling subdomain.
SESSION_COOKIE = "__Host-session"
SESSION_LIFETIME = timedelta(days=90)
TOUCH_AFTER = timedelta(days=1)

session_cookie = APIKeyCookie(name=SESSION_COOKIE, scheme_name="session", auto_error=False)


def hash_token(token: str) -> str:
    """A random 256-bit token needs no salt or slow hash: there's nothing to guess."""
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(connection: Connection, user_id: UUID, moment: datetime) -> str:
    """Keeps a new session for this user and returns its token, for the cookie only."""
    token = secrets.token_urlsafe(32)
    sessions.Querier(connection).start_session(
        id=uuid4(), user_id=user_id, token_hash=hash_token(token), last_used_at=moment
    )
    return token


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response) -> None:
    """With the attributes it was set with, or the browser keeps it."""
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="lax")


def end_session(database: Database, token: str) -> None:
    """Ends the session this token belongs to, if it's still live."""
    with database.read() as connection:
        session = sessions.Querier(connection).find_session(token_hash=hash_token(token))
    if session is None:
        return
    with database.transaction(session.user_id, "sign out") as connection:
        sessions.Querier(connection).end_session(id=session.id, user_id=session.user_id)


def current_user_id(
    response: Response,
    database: Annotated[Database, Depends(get_database)],
    moment: Annotated[datetime, Depends(clock)],
    token: Annotated[str | None, Depends(session_cookie)],
) -> UUID:
    """Who is signed in. Without a live session, a 401."""
    if not token:
        raise not_signed_in()
    with database.read() as connection:
        session = sessions.Querier(connection).find_session(token_hash=hash_token(token))
    if session is None or moment >= session.last_used_at + SESSION_LIFETIME:
        raise not_signed_in()
    if moment >= session.last_used_at + TOUCH_AFTER:
        with database.transaction(session.user_id, "use session") as connection:
            sessions.Querier(connection).touch_session(
                id=session.id, user_id=session.user_id, last_used_at=moment
            )
        set_session_cookie(response, token)
    return session.user_id


def not_signed_in() -> HTTPException:
    return HTTPException(status_code=401, detail="Not signed in")
