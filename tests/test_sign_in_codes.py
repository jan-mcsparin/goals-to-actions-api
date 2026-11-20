"""One-time codes and the command that makes them (ADR-012): run inside AWS, it adds a user and
prints their first code, or prints a new code for a user who has one. A code is long, random,
used once and gone in ten minutes; the database keeps only its hash."""

import hashlib
import re
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, text

from app.database import Database
from app.sign_in import command
from app.sign_in.codes import normalised
from app.sign_in.session import start_session
from tests.conftest import PINNED

SHOWN = re.compile(r"^([0-9A-HJKMNP-TV-Z]{4}-){4}[0-9A-HJKMNP-TV-Z]{4}$")


def run(database: Database, capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    status = command.main(list(argv), database=database, now=lambda: PINNED)
    captured = capsys.readouterr()
    return status, captured.out + captured.err


def printed_code(output: str) -> str:
    [code] = re.findall(r"([0-9A-Z]{4}(?:-[0-9A-Z]{4}){4})", output)
    return str(code)


def printed_user(output: str) -> UUID:
    [user_id] = re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", output)
    return UUID(user_id)


def codes_of(connection: Connection, user_id: UUID) -> list[dict[str, object]]:
    return [
        dict(row)
        for row in connection.execute(
            text("select code_hash, expires_at, used_at from sign_in_codes where user_id = :u"),
            {"u": user_id},
        ).mappings()
    ]


def test_add_user_makes_a_user_at_normal_intensity_with_no_weeks_opened(
    database: Database, connection: Connection, capsys: pytest.CaptureFixture[str]
) -> None:
    status, output = run(database, capsys, "add-user")

    user = connection.execute(
        text(
            "select intensity, planned_through_week, closed_through_week from users where id = :id"
        ),
        {"id": printed_user(output)},
    ).one()
    assert status == 0
    assert tuple(user) == ("normal", None, None)


def test_add_user_prints_the_new_users_first_code(
    database: Database, connection: Connection, capsys: pytest.CaptureFixture[str]
) -> None:
    _, output = run(database, capsys, "add-user")

    code = printed_code(output)
    assert SHOWN.match(code)
    [stored] = codes_of(connection, printed_user(output))
    assert stored["code_hash"] == hashlib.sha256(normalised(code).encode()).hexdigest()


def test_a_code_is_kept_as_its_hash_and_lasts_ten_minutes(
    database: Database, connection: Connection, capsys: pytest.CaptureFixture[str]
) -> None:
    _, output = run(database, capsys, "add-user")
    user_id = printed_user(output)

    status, output = run(database, capsys, "code", str(user_id))

    code = printed_code(output)
    assert status == 0
    stored = codes_of(connection, user_id)
    assert len(stored) == 2
    assert all(normalised(code) not in str(row) for row in stored)
    assert {row["expires_at"] for row in stored} == {PINNED + timedelta(minutes=10)}
    assert {row["used_at"] for row in stored} == {None}


def test_each_code_is_new(database: Database, capsys: pytest.CaptureFixture[str]) -> None:
    _, output = run(database, capsys, "add-user")
    user_id = str(printed_user(output))

    codes = {printed_code(run(database, capsys, "code", user_id)[1]) for _ in range(3)}

    assert len(codes) == 3


def test_a_code_for_an_unknown_user_is_refused(
    database: Database, capsys: pytest.CaptureFixture[str]
) -> None:
    status, output = run(database, capsys, "code", str(uuid4()))

    assert status != 0
    assert "No such user" in output


def test_making_a_code_is_in_the_audit_log(
    database: Database, connection: Connection, capsys: pytest.CaptureFixture[str]
) -> None:
    _, output = run(database, capsys, "add-user")

    actions = connection.execute(
        text("select table_name, action from audit_log where user_id = :u order by id"),
        {"u": printed_user(output)},
    ).all()

    assert [tuple(row) for row in actions] == [
        ("users", "add user"),
        ("sign_in_codes", "add user"),
    ]


@pytest.mark.parametrize(
    "typed",
    ["ABCD-EFGH-JKMN-PQRS-TVWX", "abcd efgh jkmn pqrs tvwx", " abcdefghjkmnpqrstvwx "],
)
def test_case_dashes_and_spaces_dont_matter(typed: str) -> None:
    assert normalised(typed) == "ABCDEFGHJKMNPQRSTVWX"


def test_letters_easily_misread_are_read_as_the_digits() -> None:
    assert normalised("O0IL-1") == "00111"


# Cutting someone off: a lost phone, or someone no longer trusted (security review).


def signed_in_user(database: Database, connection: Connection) -> UUID:
    """A user with two live sessions and two passkeys."""
    user_id, _ = command.add_user(database, PINNED)
    with database.transaction(user_id, "start session") as transaction:
        start_session(transaction, user_id, PINNED)
        start_session(transaction, user_id, PINNED)
    for credential_id in (f"one-{user_id}", f"two-{user_id}"):
        connection.execute(
            text(
                "insert into passkeys (id, user_id, credential_id, public_key, sign_count)"
                " values (:id, :user_id, :credential_id, 'key', 0)"
            ),
            {"id": uuid4(), "user_id": user_id, "credential_id": credential_id},
        )
    return user_id


def live(connection: Connection, table: str, user_id: UUID) -> int:
    return int(
        connection.execute(
            text(f"select count(*) from {table} where user_id = :u and deleted_at is null"),
            {"u": user_id},
        ).scalar_one()
    )


def test_end_sessions_signs_a_user_out_everywhere(
    database: Database, connection: Connection, capsys: pytest.CaptureFixture[str]
) -> None:
    user_id = signed_in_user(database, connection)

    status, output = run(database, capsys, "end-sessions", str(user_id))

    assert status == 0
    assert "Sessions ended: 2" in output
    assert live(connection, "sessions", user_id) == 0
    assert live(connection, "passkeys", user_id) == 2


def test_end_sessions_leaves_other_users_signed_in(
    database: Database, connection: Connection, capsys: pytest.CaptureFixture[str]
) -> None:
    user_id = signed_in_user(database, connection)
    other = signed_in_user(database, connection)

    run(database, capsys, "end-sessions", str(user_id))

    assert live(connection, "sessions", other) == 2


def test_remove_passkeys_removes_every_passkey_of_a_user(
    database: Database, connection: Connection, capsys: pytest.CaptureFixture[str]
) -> None:
    user_id = signed_in_user(database, connection)
    other = signed_in_user(database, connection)

    status, output = run(database, capsys, "remove-passkeys", str(user_id))

    assert status == 0
    assert "Passkeys removed: 2" in output
    assert "Sessions ended: 2" in output
    assert live(connection, "passkeys", user_id) == 0
    assert live(connection, "passkeys", other) == 2


def test_removing_passkeys_signs_the_user_out_everywhere(
    database: Database, connection: Connection, capsys: pytest.CaptureFixture[str]
) -> None:
    """Someone no longer trusted is cut off now, not when their sessions run out."""
    user_id = signed_in_user(database, connection)
    other = signed_in_user(database, connection)

    run(database, capsys, "remove-passkeys", str(user_id))

    assert live(connection, "sessions", user_id) == 0
    assert live(connection, "sessions", other) == 2


def test_removing_passkeys_is_in_the_audit_log(
    database: Database, connection: Connection, capsys: pytest.CaptureFixture[str]
) -> None:
    user_id = signed_in_user(database, connection)

    run(database, capsys, "remove-passkeys", str(user_id))

    actions = connection.execute(
        text(
            "select action from audit_log"
            " where table_name = 'passkeys' and operation = 'update' and user_id = :u"
        ),
        {"u": user_id},
    ).scalars()
    assert list(actions) == ["remove passkeys", "remove passkeys"]


@pytest.mark.parametrize("subcommand", ["end-sessions", "remove-passkeys"])
def test_cutting_off_an_unknown_user_is_refused(
    subcommand: str, database: Database, capsys: pytest.CaptureFixture[str]
) -> None:
    status, output = run(database, capsys, subcommand, str(uuid4()))

    assert status != 0
    assert "No such user" in output
