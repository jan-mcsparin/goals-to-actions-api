import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.exc import OperationalError

from app.database import Database

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
