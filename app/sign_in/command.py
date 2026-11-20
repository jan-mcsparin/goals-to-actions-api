"""Adding a user, a code to add a passkey, and cutting someone off (ADR-012). Run inside AWS by
someone signed in to the AWS account, which is the root of trust; locally, against the
development database:

    uv run python -m app.sign_in.command add-user
    uv run python -m app.sign_in.command code <user-id>
    uv run python -m app.sign_in.command end-sessions <user-id>      # a lost phone
    uv run python -m app.sign_in.command remove-passkeys <user-id>   # no longer trusted
"""

import argparse
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.database import Database, database
from app.db import passkeys, sessions, users
from app.sign_in.codes import make_code


def add_user(database: Database, moment: datetime) -> tuple[UUID, str]:
    """A new user at Normal intensity with no weeks opened, and their first code. Their first
    request that needs the day opens their week."""
    user_id = uuid4()
    with database.transaction(user_id, "add user") as connection:
        users.Querier(connection).add_user(id=user_id)
        return user_id, make_code(connection, user_id, moment)


def user_exists(database: Database, user_id: UUID) -> bool:
    with database.read() as connection:
        return users.Querier(connection).get_user(id=user_id) is not None


def code_for(database: Database, user_id: UUID, moment: datetime) -> str:
    """A new code for an existing user."""
    with database.transaction(user_id, "make sign-in code") as connection:
        return make_code(connection, user_id, moment)


def end_sessions(database: Database, user_id: UUID) -> int:
    """Signs the user out on every device. Returns how many sessions ended."""
    with database.transaction(user_id, "end sessions") as connection:
        return sessions.Querier(connection).end_user_sessions(user_id=user_id)


def remove_passkeys(database: Database, user_id: UUID) -> int:
    """Removes every passkey of the user; only a new code lets them add one again. Returns how
    many were removed."""
    with database.transaction(user_id, "remove passkeys") as connection:
        return passkeys.Querier(connection).remove_user_passkeys(user_id=user_id)


def main(
    argv: list[str] | None = None,
    database: Database = database,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.sign_in.command")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("add-user", help="add a user and print their first code")
    for name, help in (
        ("code", "print a new code for a user"),
        ("end-sessions", "sign a user out on every device"),
        ("remove-passkeys", "remove every passkey of a user"),
    ):
        commands.add_parser(name, help=help).add_argument("user_id", type=UUID)
    arguments = parser.parse_args(argv)

    if arguments.command == "add-user":
        user_id, code = add_user(database, now())
        print(f"Added user {user_id}")
        print(f"Code: {code} (works once, for ten minutes)")
        return 0

    user_id = arguments.user_id
    if not user_exists(database, user_id):
        print(f"No such user: {user_id}", file=sys.stderr)
        return 1
    if arguments.command == "code":
        print(f"Code: {code_for(database, user_id, now())} (works once, for ten minutes)")
    elif arguments.command == "end-sessions":
        print(f"Ended {end_sessions(database, user_id)} sessions")
    else:
        print(f"Removed {remove_passkeys(database, user_id)} passkeys")
    return 0


if __name__ == "__main__":
    sys.exit(main())
