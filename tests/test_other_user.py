"""A second user can't read or change the first's rows through any route (spec `sign-in`).
With invited testers this is a requirement: it's the test the owner-in-every-query rule has been
waiting for. It runs over every operation in the schema and fails for one without a case.

The first user (the fixed user) arranges their rows; then the same request goes out with the
second user's session. Their rows must be as they were, and no id of theirs may come back."""

from collections.abc import Callable
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.config import FIXED_USER_ID
from app.database import Database
from app.sign_in.session import SESSION_COOKIE, start_session
from tests.conftest import PINNED, FixedClock
from tests.test_goals import ZONE
from tests.test_repeats import CASES, Given, aspiration, goal, ok, snapshot, user_tables

# The sign-in routes act on no one's rows: they're how a session starts or ends.
OPEN = {"health", "redeemCode", "addPasskey", "startSignIn", "finishSignIn", "signOut"}

# Creates whose id the device makes: sent again by the second user with the first's id.
CREATES = [
    "createAspiration",
    "createGoal",
    "addMilestone",
    "checkIn",
    "createRecurringItem",
    "addTask",
]

ReadArrange = Callable[[Given], str]


def made(given: Given, operation: str) -> None:
    """The first user makes something with one of the repeat test's writes."""
    method, path, body = CASES[operation](given)
    ok(given.client.request(method, path, json=body))


def list_aspirations(given: Given) -> str:
    aspiration(given.client)
    return "/api/aspirations"


def list_goals(given: Given) -> str:
    goal(given.client)
    return "/api/goals"


def get_goal(given: Given) -> str:
    return f"/api/goals/{goal(given.client)}"


def list_recurring_items(given: Given) -> str:
    made(given, "createRecurringItem")
    return "/api/recurring-items"


def get_settings(given: Given) -> str:
    return "/api/settings"


def get_week(given: Given) -> str:
    made(given, "addTask")
    return "/api/weeks/2026-11-16"


def get_upcoming(given: Given) -> str:
    ok(given.client.put(f"/api/tasks/{uuid4()}", json={"title": "Renew", "dueDate": "2027-01-15"}))
    return "/api/tasks/upcoming"


READS: dict[str, ReadArrange] = {
    "listAspirations": list_aspirations,
    "listGoals": list_goals,
    "getGoal": get_goal,
    "listRecurringItems": list_recurring_items,
    "getSettings": get_settings,
    "getWeek": get_week,
    "getUpcoming": get_upcoming,
}


@pytest.fixture
def second_user(database: Database, connection: Connection) -> str:
    """Another user, signed in: their session's token."""
    user_id = uuid4()
    connection.execute(text("insert into users (id) values (:id)"), {"id": user_id})
    with database.transaction(user_id, "start session") as transaction:
        return start_session(transaction, user_id, PINNED)


@pytest.fixture
def zoned(client: TestClient) -> TestClient:
    client.headers["X-Time-Zone"] = ZONE
    return client


def first_users_ids(connection: Connection) -> set[str]:
    ids = {str(FIXED_USER_ID)}
    for table in user_tables(connection):
        ids |= {
            str(row_id)
            for row_id in connection.execute(
                text(f"select id from {table} where user_id = :user_id"), {"user_id": FIXED_USER_ID}
            ).scalars()
        }
    return ids


def as_second_user(client: TestClient, token: str) -> None:
    """Clears the jar first: a request after the clock moved a day may have had the first
    user's cookie sent again, for the test server's host."""
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, token)


def leaked(ids: set[str], answer: str) -> set[str]:
    return {row_id for row_id in ids if row_id in answer}


@pytest.mark.parametrize("operation", CASES)
def test_a_second_user_cant_change_the_first_users_rows(
    operation: str,
    zoned: TestClient,
    connection: Connection,
    fixed_clock: FixedClock,
    second_user: str,
) -> None:
    method, path, body = CASES[operation](Given(zoned, connection, fixed_clock))
    before = snapshot(connection)
    ids = first_users_ids(connection)

    as_second_user(zoned, second_user)
    response = zoned.request(method, path, json=body)

    assert snapshot(connection) == before
    assert leaked(ids, response.text) == set(), response.text


@pytest.mark.parametrize("operation", CREATES)
def test_a_second_user_cant_create_with_the_first_users_id(
    operation: str,
    zoned: TestClient,
    connection: Connection,
    fixed_clock: FixedClock,
    second_user: str,
) -> None:
    method, path, body = CASES[operation](Given(zoned, connection, fixed_clock))
    ok(zoned.request(method, path, json=body))
    before = snapshot(connection)
    ids = first_users_ids(connection)

    as_second_user(zoned, second_user)
    response = zoned.request(method, path, json=body)

    assert response.status_code in (404, 409), response.text
    assert snapshot(connection) == before
    assert leaked(ids, response.text) == set(), response.text


@pytest.mark.parametrize("operation", READS)
def test_a_second_user_cant_read_the_first_users_rows(
    operation: str,
    zoned: TestClient,
    connection: Connection,
    fixed_clock: FixedClock,
    second_user: str,
) -> None:
    path = READS[operation](Given(zoned, connection, fixed_clock))
    ids = first_users_ids(connection)
    first = zoned.get(path)
    assert first.status_code == 200, first.text
    if operation != "getSettings":  # settings hold no ids
        assert leaked(ids, first.text), "the first user should see their own rows"

    as_second_user(zoned, second_user)
    response = zoned.get(path)

    assert response.status_code in (200, 404), response.text
    assert leaked(ids, response.text) == set(), response.text


def test_every_operation_has_a_case(client: TestClient) -> None:
    schema = client.get("/api/openapi.json").json()
    operations = {
        operation["operationId"]
        for methods in schema["paths"].values()
        for operation in methods.values()
    }

    assert operations - OPEN - CASES.keys() - READS.keys() == set()
