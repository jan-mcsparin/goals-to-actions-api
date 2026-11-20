"""A session: a row holding the hash of a random token, and the token in a `__Host-` cookie
(ADR-012). It lasts 90 days from its last use, and last use is written at most once a day."""

import hashlib
from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.config import FIXED_USER_ID
from app.database import Database
from app.sign_in.session import SESSION_COOKIE, start_session
from tests.conftest import PINNED, FixedClock

DAY = timedelta(days=1)


def last_used(connection: Connection, token: str) -> object:
    return connection.execute(
        text("select last_used_at from sessions where token_hash = :hash"),
        {"hash": hashlib.sha256(token.encode()).hexdigest()},
    ).scalar_one()


def test_a_session_reads_its_users_rows(client: TestClient) -> None:
    client.put(f"/api/aspirations/{uuid4()}", json={"name": "Be healthy"})

    names = [
        aspiration["name"] for aspiration in client.get("/api/aspirations").json()["aspirations"]
    ]

    assert names == ["Be healthy"]


def test_the_database_holds_only_the_tokens_hash(
    database: Database, connection: Connection
) -> None:
    with database.transaction(FIXED_USER_ID, "start session") as transaction:
        token = start_session(transaction, FIXED_USER_ID, PINNED)

    stored = connection.execute(
        text("select token_hash from sessions where user_id = :user_id"),
        {"user_id": FIXED_USER_ID},
    ).scalars()

    assert hashlib.sha256(token.encode()).hexdigest() in list(stored)
    assert len(token) >= 43  # 32 random bytes, URL-safe


def test_an_unknown_token_is_refused(client: TestClient) -> None:
    client.cookies.set(SESSION_COOKIE, "not-a-session")

    assert client.get("/api/aspirations").status_code == 401


def test_an_ended_session_is_refused(client: TestClient, connection: Connection) -> None:
    connection.execute(text("update sessions set deleted_at = now()"))

    assert client.get("/api/aspirations").status_code == 401


def test_a_session_lasts_90_days_from_its_last_use(
    client: TestClient, fixed_clock: FixedClock
) -> None:
    fixed_clock.instant = PINNED + 90 * DAY - timedelta(minutes=1)
    assert client.get("/api/aspirations").status_code == 200

    fixed_clock.instant = fixed_clock.instant + 90 * DAY - timedelta(minutes=1)
    assert client.get("/api/aspirations").status_code == 200


def test_a_session_unused_for_90_days_is_refused(
    client: TestClient, fixed_clock: FixedClock
) -> None:
    fixed_clock.instant = PINNED + 90 * DAY

    assert client.get("/api/aspirations").status_code == 401


def test_last_use_is_written_once_in_a_day_of_many_requests(
    client: TestClient, connection: Connection, fixed_clock: FixedClock
) -> None:
    token = client.cookies[SESSION_COOKIE]

    for hours in (1, 5, 23):
        fixed_clock.instant = PINNED + timedelta(hours=hours)
        response = client.get("/api/aspirations")
        assert "set-cookie" not in response.headers

    assert last_used(connection, token) == PINNED


def test_a_new_day_writes_last_use_and_sends_the_cookie_again(
    client: TestClient, connection: Connection, fixed_clock: FixedClock
) -> None:
    token = client.cookies[SESSION_COOKIE]
    fixed_clock.instant = PINNED + DAY

    cookie = client.get("/api/aspirations").headers["set-cookie"]

    assert last_used(connection, token) == PINNED + DAY
    assert cookie.startswith(f"{SESSION_COOKIE}={token};")
    for flag in ("HttpOnly", "Max-Age=7776000", "Path=/", "SameSite=lax", "Secure"):
        assert flag in cookie
    assert "Domain" not in cookie
