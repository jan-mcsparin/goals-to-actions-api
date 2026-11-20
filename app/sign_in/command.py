"""Adding a user, and a code to add a passkey (ADR-012). Run inside AWS by someone signed in to
the AWS account, which is the root of trust; locally, against the development database:

    uv run python -m app.sign_in.command add-user
    uv run python -m app.sign_in.command code <user-id>
"""

import argparse
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.database import Database, database
from app.db import users
from app.sign_in.codes import make_code


def add_user(database: Database, moment: datetime) -> tuple[UUID, str]:
    """A new user at Normal intensity with no weeks opened, and their first code. Their first
    request that needs the day opens their week."""
    user_id = uuid4()
    with database.transaction(user_id, "add user") as connection:
        users.Querier(connection).add_user(id=user_id)
        return user_id, make_code(connection, user_id, moment)


def code_for(database: Database, user_id: UUID, moment: datetime) -> str | None:
    """A new code for an existing user, or None if there's no such user."""
    with database.transaction(user_id, "make sign-in code") as connection:
        if users.Querier(connection).get_user(id=user_id) is None:
            return None
        return make_code(connection, user_id, moment)


def main(
    argv: list[str] | None = None,
    database: Database = database,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.sign_in.command")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("add-user", help="add a user and print their first code")
    code = commands.add_parser("code", help="print a new code for a user")
    code.add_argument("user_id", type=UUID)
    arguments = parser.parse_args(argv)

    if arguments.command == "add-user":
        user_id, made = add_user(database, now())
        print(f"Added user {user_id}")
    else:
        user_id = arguments.user_id
        found = code_for(database, user_id, now())
        if found is None:
            print(f"No such user: {user_id}", file=sys.stderr)
            return 1
        made = found
    print(f"Code: {made} (works once, for ten minutes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
