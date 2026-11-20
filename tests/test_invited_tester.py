"""An invited tester, end to end (ADR-012, revisited 2026-11-19): the command adds them and
prints a code; they redeem it and add a passkey; their first request that needs the day opens
their week; they see only their own rows. The passkey check is stood in for, as elsewhere."""

import re
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.database import Database
from app.sign_in import command, rules
from app.sign_in.session import SESSION_COOKIE
from tests.conftest import PINNED
from tests.test_goals import ZONE


def test_an_invited_tester_signs_in_and_their_first_week_opens(
    client: TestClient,
    database: Database,
    connection: Connection,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client.put(f"/api/aspirations/{uuid4()}", json={"name": "The founder's"})
    command.main(["add-user"], database=database, now=lambda: PINNED)
    output = capsys.readouterr().out
    [user_id] = re.findall(r"Added user (\S+)", output)
    [code] = re.findall(r"Code: (\S+)", output)
    monkeypatch.setattr(
        rules,
        "verify_registration_response",
        lambda **_: SimpleNamespace(credential_id=b"c", credential_public_key=b"k", sign_count=0),
    )

    client.cookies.clear()
    challenge_id = client.post("/api/sign-in/code", json={"code": code}).json()["challengeId"]
    added = client.post(
        "/api/sign-in/passkeys", json={"challengeId": challenge_id, "credential": {"id": "c"}}
    )
    client.cookies.set(SESSION_COOKIE, added.cookies[SESSION_COOKIE])
    client.headers["X-Time-Zone"] = ZONE
    opened_before = connection.execute(
        text("select planned_through_week from users where id = :id"), {"id": user_id}
    ).scalar_one()
    week: Any = client.get("/api/weeks/2026-11-16")

    assert opened_before is None
    assert week.status_code == 200, week.text
    planned = connection.execute(
        text("select planned_through_week, intensity from users where id = :id"), {"id": user_id}
    ).one()
    assert (planned.planned_through_week.isoformat(), planned.intensity) == ("2026-11-16", "normal")
    assert client.get("/api/settings").json() == {"intensity": "normal"}
    assert client.get("/api/aspirations").json() == {"aspirations": []}
