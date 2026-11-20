"""Signing in with a passkey (ADR-012): start makes a challenge with no user named; the passkey
the browser signs it with says whose it is. The library checks the signature; refusals go
through the real library, and an accepted signature through a stand-in for its check."""

from collections.abc import Iterator
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.database import Database
from app.sign_in import rules
from app.sign_in.command import add_user
from app.sign_in.session import SESSION_COOKIE
from tests.conftest import PINNED, FixedClock

START = "/api/sign-in/start"
FINISH = "/api/sign-in/finish"
CREDENTIAL_ID = "Y3JlZGVudGlhbA"
PUBLIC_KEY = "cHVibGljLWtleQ"


@pytest.fixture
def owner(database: Database, connection: Connection) -> UUID:
    """A user with one passkey, kept as adding it would keep it."""
    user_id, _ = add_user(database, PINNED)
    connection.execute(
        text(
            "insert into passkeys (id, user_id, credential_id, public_key, sign_count)"
            " values (:id, :user_id, :credential_id, :public_key, 3)"
        ),
        {
            "id": uuid4(),
            "user_id": user_id,
            "credential_id": CREDENTIAL_ID,
            "public_key": PUBLIC_KEY,
        },
    )
    return user_id


@pytest.fixture
def signed_out(client: TestClient) -> Iterator[TestClient]:
    client.cookies.clear()
    yield client


@pytest.fixture
def accepted(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Stands in for the library's check, accepting any signature. Records each call."""
    calls: list[dict[str, Any]] = []

    def verify(**given: Any) -> SimpleNamespace:
        calls.append(given)
        return SimpleNamespace(new_sign_count=4)

    monkeypatch.setattr(rules, "verify_authentication_response", verify)
    return calls


def credential(credential_id: str = CREDENTIAL_ID) -> dict[str, Any]:
    return {"id": credential_id, "rawId": credential_id, "type": "public-key", "response": {}}


def finish(client: TestClient, credential_id: str = CREDENTIAL_ID) -> Any:
    challenge_id = client.post(START).json()["challengeId"]
    return client.post(
        FINISH, json={"challengeId": challenge_id, "credential": credential(credential_id)}
    )


def sessions_of(connection: Connection, user_id: UUID) -> int:
    return int(
        connection.execute(
            text("select count(*) from sessions where user_id = :u"), {"u": user_id}
        ).scalar_one()
    )


def test_start_returns_options_naming_no_one(signed_out: TestClient) -> None:
    response = signed_out.post(START)

    assert response.status_code == 200, response.text
    UUID(response.json()["challengeId"])
    options = response.json()["options"]
    assert options["rpId"] == "localhost"
    assert options["challenge"]
    assert options["userVerification"] == "required"
    assert not options.get("allowCredentials")


def test_an_accepted_passkey_signs_its_owner_in(
    signed_out: TestClient, connection: Connection, owner: UUID, accepted: list[dict[str, Any]]
) -> None:
    response = finish(signed_out)

    assert response.status_code == 204, response.text
    assert sessions_of(connection, owner) == 1
    signed_out.cookies.set(SESSION_COOKIE, response.cookies[SESSION_COOKIE])
    assert signed_out.get("/api/aspirations").json() == {"aspirations": []}


def test_signing_in_keeps_the_new_sign_count(
    signed_out: TestClient, connection: Connection, owner: UUID, accepted: list[dict[str, Any]]
) -> None:
    finish(signed_out)

    sign_count = connection.execute(
        text("select sign_count from passkeys where user_id = :u"), {"u": owner}
    ).scalar_one()
    assert sign_count == 4


def test_the_library_checks_against_the_kept_key_and_count(
    signed_out: TestClient, owner: UUID, accepted: list[dict[str, Any]]
) -> None:
    finish(signed_out)

    [call] = accepted
    assert call["credential"] == credential()
    assert call["credential_public_key"] == b"public-key"
    assert call["credential_current_sign_count"] == 3
    assert call["expected_rp_id"] == "localhost"
    assert call["expected_origin"] == "http://localhost:5173"
    assert call["require_user_verification"] is True
    assert isinstance(call["expected_challenge"], bytes) and call["expected_challenge"]


def test_an_unknown_passkey_is_refused(
    signed_out: TestClient, owner: UUID, accepted: list[dict[str, Any]]
) -> None:
    response = finish(signed_out, "dW5rbm93bg")

    assert response.status_code == 401
    assert response.json() == {"detail": "That didn't work"}


def test_a_signature_the_library_rejects_is_refused(
    signed_out: TestClient, connection: Connection, owner: UUID
) -> None:
    response = finish(signed_out)

    assert response.status_code == 401
    assert "set-cookie" not in response.headers
    assert sessions_of(connection, owner) == 0


def test_a_deleted_passkey_is_refused(
    signed_out: TestClient, connection: Connection, owner: UUID, accepted: list[dict[str, Any]]
) -> None:
    connection.execute(text("update passkeys set deleted_at = now()"))

    assert finish(signed_out).status_code == 401


def test_a_challenge_works_once(
    signed_out: TestClient, owner: UUID, accepted: list[dict[str, Any]]
) -> None:
    challenge_id = signed_out.post(START).json()["challengeId"]
    body = {"challengeId": challenge_id, "credential": credential()}
    signed_out.post(FINISH, json=body)

    assert signed_out.post(FINISH, json=body).status_code == 401


def test_a_challenge_is_gone_after_five_minutes(
    signed_out: TestClient, owner: UUID, accepted: list[dict[str, Any]], fixed_clock: FixedClock
) -> None:
    challenge_id = signed_out.post(START).json()["challengeId"]
    fixed_clock.instant = PINNED + timedelta(minutes=5)

    response = signed_out.post(
        FINISH, json={"challengeId": challenge_id, "credential": credential()}
    )

    assert response.status_code == 401


def test_a_challenge_for_adding_a_passkey_cant_finish_a_sign_in(
    signed_out: TestClient, database: Database, owner: UUID, accepted: list[dict[str, Any]]
) -> None:
    _, code = add_user(database, PINNED)
    challenge_id = signed_out.post("/api/sign-in/code", json={"code": code}).json()["challengeId"]

    response = signed_out.post(
        FINISH, json={"challengeId": challenge_id, "credential": credential()}
    )

    assert response.status_code == 401


def test_starting_a_sign_in_clears_expired_challenges(
    signed_out: TestClient, connection: Connection, fixed_clock: FixedClock
) -> None:
    """`startSignIn` needs no session, so its rows can't be left to pile up (security review)."""
    for _ in range(3):
        signed_out.post(START)
    fixed_clock.instant = PINNED + timedelta(minutes=5)

    signed_out.post(START)

    left = connection.execute(text("select count(*) from sign_in_challenges")).scalar_one()
    assert left == 1


def test_any_failure_in_the_librarys_check_is_a_401(
    signed_out: TestClient, owner: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    def malformed(**_: Any) -> None:
        raise IndexError("short data")

    monkeypatch.setattr(rules, "verify_authentication_response", malformed)

    assert finish(signed_out).status_code == 401


def test_signing_in_again_ends_the_devices_old_session(
    client: TestClient, connection: Connection, owner: UUID, accepted: list[dict[str, Any]]
) -> None:
    """The device's earlier session can't outlive the new one (security review)."""
    old = client.cookies[SESSION_COOKIE]

    assert finish(client).status_code == 204

    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, old)
    assert client.get("/api/aspirations").status_code == 401


def test_a_refused_sign_in_leaves_the_devices_session(client: TestClient, owner: UUID) -> None:
    response = finish(client)

    assert response.status_code == 401
    assert client.get("/api/aspirations").status_code == 200
