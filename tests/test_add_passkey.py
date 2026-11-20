"""Adding a passkey with a one-time code (ADR-012): the code is redeemed for the browser's
registration options and a challenge; the credential the browser makes is checked by the
WebAuthn library, kept, and starts a session. Tests don't act out a passkey: refusals go
through the real library, and an accepted credential through a stand-in for its check."""

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

REDEEM = "/api/sign-in/code"
ADD = "/api/sign-in/passkeys"
CREDENTIAL = {"id": "made-up", "rawId": "made-up", "type": "public-key", "response": {}}


@pytest.fixture
def tester(database: Database) -> tuple[UUID, str]:
    """An invited tester and their first code, as the command makes them."""
    return add_user(database, PINNED)


@pytest.fixture
def signed_out(client: TestClient) -> Iterator[TestClient]:
    client.cookies.clear()
    yield client


@pytest.fixture
def accepted(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Stands in for the library's check, accepting any credential. Records each call."""
    calls: list[dict[str, Any]] = []

    def verify(**given: Any) -> SimpleNamespace:
        calls.append(given)
        return SimpleNamespace(
            credential_id=b"credential-" + uuid4().bytes,
            credential_public_key=b"public-key",
            sign_count=0,
        )

    monkeypatch.setattr(rules, "verify_registration_response", verify)
    return calls


def redeem(client: TestClient, code: str) -> Any:
    return client.post(REDEEM, json={"code": code})


def passkeys_of(connection: Connection, user_id: UUID) -> list[Any]:
    return list(
        connection.execute(
            text("select credential_id, public_key, sign_count from passkeys where user_id = :u"),
            {"u": user_id},
        )
    )


def sessions_of(connection: Connection, user_id: UUID) -> int:
    return int(
        connection.execute(
            text("select count(*) from sessions where user_id = :u"), {"u": user_id}
        ).scalar_one()
    )


# redeemCode


def test_a_code_is_redeemed_for_registration_options(
    signed_out: TestClient, tester: tuple[UUID, str]
) -> None:
    user_id, code = tester

    response = redeem(signed_out, code)

    assert response.status_code == 200, response.text
    found = response.json()
    UUID(found["challengeId"])
    options = found["options"]
    assert options["rp"]["id"] == "localhost"
    assert options["challenge"]
    assert options["attestation"] == "none"
    assert options["authenticatorSelection"]["residentKey"] == "required"
    assert options["authenticatorSelection"]["userVerification"] == "required"


def test_a_code_works_once(signed_out: TestClient, tester: tuple[UUID, str]) -> None:
    _, code = tester
    redeem(signed_out, code)

    response = redeem(signed_out, code)

    assert response.status_code == 401
    assert response.json() == {"detail": "That didn't work"}


def test_a_wrong_code_is_refused(signed_out: TestClient, tester: tuple[UUID, str]) -> None:
    assert redeem(signed_out, "AAAA-AAAA-AAAA-AAAA-AAAA").status_code == 401


def test_a_code_works_for_ten_minutes(
    signed_out: TestClient, tester: tuple[UUID, str], fixed_clock: FixedClock
) -> None:
    fixed_clock.instant = PINNED + timedelta(minutes=9, seconds=59)

    assert redeem(signed_out, tester[1]).status_code == 200


def test_a_code_is_gone_after_ten_minutes(
    signed_out: TestClient, tester: tuple[UUID, str], fixed_clock: FixedClock
) -> None:
    fixed_clock.instant = PINNED + timedelta(minutes=10)

    assert redeem(signed_out, tester[1]).status_code == 401


def test_a_code_typed_in_lower_case_without_dashes_works(
    signed_out: TestClient, tester: tuple[UUID, str]
) -> None:
    typed = tester[1].replace("-", " ").lower()

    assert redeem(signed_out, typed).status_code == 200


# addPasskey


def test_an_accepted_passkey_is_kept_and_starts_a_session(
    signed_out: TestClient,
    connection: Connection,
    tester: tuple[UUID, str],
    accepted: list[dict[str, Any]],
) -> None:
    user_id, code = tester
    challenge_id = redeem(signed_out, code).json()["challengeId"]

    response = signed_out.post(ADD, json={"challengeId": challenge_id, "credential": CREDENTIAL})

    assert response.status_code == 204, response.text
    [kept] = passkeys_of(connection, user_id)
    assert kept.sign_count == 0
    assert sessions_of(connection, user_id) == 1
    cookie = response.headers["set-cookie"]
    for flag in ("HttpOnly", "Secure", "SameSite=lax", "Path=/"):
        assert flag in cookie
    signed_out.cookies.set(SESSION_COOKIE, response.cookies[SESSION_COOKIE])
    assert signed_out.get("/api/aspirations").json() == {"aspirations": []}


def test_the_library_checks_the_challenge_origin_and_user_verification(
    signed_out: TestClient, tester: tuple[UUID, str], accepted: list[dict[str, Any]]
) -> None:
    challenge_id = redeem(signed_out, tester[1]).json()["challengeId"]

    signed_out.post(ADD, json={"challengeId": challenge_id, "credential": CREDENTIAL})

    [call] = accepted
    assert call["credential"] == CREDENTIAL
    assert call["expected_rp_id"] == "localhost"
    assert call["expected_origin"] == "http://localhost:5173"
    assert call["require_user_verification"] is True
    assert isinstance(call["expected_challenge"], bytes) and call["expected_challenge"]


def test_a_credential_the_library_rejects_keeps_nothing(
    signed_out: TestClient, connection: Connection, tester: tuple[UUID, str]
) -> None:
    user_id, code = tester
    challenge_id = redeem(signed_out, code).json()["challengeId"]

    response = signed_out.post(ADD, json={"challengeId": challenge_id, "credential": CREDENTIAL})

    assert response.status_code == 401
    assert "set-cookie" not in response.headers
    assert passkeys_of(connection, user_id) == []
    assert sessions_of(connection, user_id) == 0


def test_a_challenge_works_once(
    signed_out: TestClient, tester: tuple[UUID, str], accepted: list[dict[str, Any]]
) -> None:
    challenge_id = redeem(signed_out, tester[1]).json()["challengeId"]
    body = {"challengeId": challenge_id, "credential": CREDENTIAL}
    signed_out.post(ADD, json=body)

    assert signed_out.post(ADD, json=body).status_code == 401


def test_a_rejected_credential_spends_the_challenge(
    signed_out: TestClient, tester: tuple[UUID, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    challenge_id = redeem(signed_out, tester[1]).json()["challengeId"]
    body = {"challengeId": challenge_id, "credential": CREDENTIAL}
    signed_out.post(ADD, json=body)

    monkeypatch.setattr(
        rules,
        "verify_registration_response",
        lambda **_: SimpleNamespace(credential_id=b"c", credential_public_key=b"k", sign_count=0),
    )
    assert signed_out.post(ADD, json=body).status_code == 401


def test_a_challenge_is_gone_after_five_minutes(
    signed_out: TestClient,
    tester: tuple[UUID, str],
    fixed_clock: FixedClock,
    accepted: list[dict[str, Any]],
) -> None:
    challenge_id = redeem(signed_out, tester[1]).json()["challengeId"]
    fixed_clock.instant = PINNED + timedelta(minutes=5)

    response = signed_out.post(ADD, json={"challengeId": challenge_id, "credential": CREDENTIAL})

    assert response.status_code == 401


def test_an_unknown_challenge_is_refused(
    signed_out: TestClient, accepted: list[dict[str, Any]]
) -> None:
    response = signed_out.post(ADD, json={"challengeId": str(uuid4()), "credential": CREDENTIAL})

    assert response.status_code == 401
