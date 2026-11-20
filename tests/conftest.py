import os
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.exc import OperationalError

from app.config import FIXED_USER_ID
from app.database import Database, get_database
from app.main import app
from app.sign_in.session import SESSION_COOKIE, start_session
from app.time_zone import clock

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://gta:gta@localhost:5432/gta_test"
)


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    """The test database. Only tests that ask for it connect, so the rest run without Postgres."""
    engine = create_engine(TEST_DATABASE_URL)
    try:
        with engine.connect():
            pass
    except OperationalError:
        pytest.fail(
            "Can't reach the test database. Start Postgres with `podman compose up -d` "
            "and migrate it with `bin/dbmate --test up`."
        )
    yield engine
    engine.dispose()


@pytest.fixture
def connection(test_engine: Engine) -> Iterator[Connection]:
    """A connection inside a transaction that's rolled back, so nothing a test writes is kept."""
    with test_engine.connect() as connection:
        outer = connection.begin()
        try:
            yield connection
        finally:
            outer.rollback()


@pytest.fixture
def database(connection: Connection) -> Database:
    """The app's Database on the test connection: each transaction() is a savepoint."""
    return Database(connection)


# Noon on Wednesday 18 Nov 2026 in Denver. No test reads the real date.
PINNED = datetime(2026, 11, 18, 19, 0, tzinfo=UTC)


class FixedClock:
    """The moment every request sees. A test sets `instant` to move it."""

    def __init__(self) -> None:
        self.instant = PINNED

    def __call__(self) -> datetime:
        return self.instant


@pytest.fixture
def fixed_clock() -> FixedClock:
    return FixedClock()


def keep_signed_in(connection: Connection, moment: datetime) -> None:
    """For a test that moves the clock past a session's 90 days: the person used the app
    in between, so their session is still live at `moment`."""
    connection.execute(text("update sessions set last_used_at = :moment"), {"moment": moment})


@pytest.fixture
def client(database: Database, fixed_clock: FixedClock) -> Iterator[TestClient]:
    """The API on the test connection, so what a request writes is rolled back too. Signed in
    as the fixed user by a session row made directly: tests don't act out a passkey. Over
    HTTPS, since the session cookie is `Secure`."""
    app.dependency_overrides[get_database] = lambda: database
    app.dependency_overrides[clock] = fixed_clock
    with database.transaction(FIXED_USER_ID, "start session") as connection:
        token = start_session(connection, FIXED_USER_ID, fixed_clock.instant)
    yield TestClient(app, base_url="https://testserver", cookies={SESSION_COOKIE: token})
    app.dependency_overrides.clear()
