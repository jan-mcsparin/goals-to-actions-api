"""One-time codes (ADR-012): 20 characters from Crockford's base 32, 100 random bits, shown
in five groups of four. Typed back, case, dashes and spaces don't matter, and the letters
easily misread as digits are read as them. Only the SHA-256 is kept."""

import hashlib
import secrets
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import Connection

from app.db import sign_in_codes

# Crockford's base 32: no I, L, O or U.
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
CODE_LENGTH = 20
GROUP = 4
CODE_LIFETIME = timedelta(minutes=10)
MISREAD = str.maketrans({"O": "0", "I": "1", "L": "1", "-": None, " ": None})


def normalised(typed: str) -> str:
    return typed.strip().upper().translate(MISREAD)


def code_hash(typed: str) -> str:
    """A random 100-bit code that lasts ten minutes needs no salt or slow hash."""
    return hashlib.sha256(normalised(typed).encode()).hexdigest()


def shown(code: str) -> str:
    return "-".join(code[start : start + GROUP] for start in range(0, len(code), GROUP))


def make_code(connection: Connection, user_id: UUID, moment: datetime) -> str:
    """Keeps a new code for this user and returns it, as shown, to be printed once."""
    code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
    sign_in_codes.Querier(connection).make_code(
        id=uuid4(), user_id=user_id, code_hash=code_hash(code), expires_at=moment + CODE_LIFETIME
    )
    return shown(code)
