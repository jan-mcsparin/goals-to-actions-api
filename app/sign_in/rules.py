"""The passkey steps (ADR-012). The checks are the WebAuthn library's, never ours. Unlike other
slices' rules these take the database, not one connection: a challenge is spent in a write of
its own, so a credential that's refused can't be tried against it again.

Every refusal is `SignInFailed`, one answer for all of them, so nothing tells a guesser which
part was wrong."""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from webauthn import (
    base64url_to_bytes,
    generate_registration_options,
    options_to_json,
    verify_registration_response,
)
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.config import APP_NAME, APP_ORIGIN, PASSKEY_RP_ID
from app.database import Database
from app.db import passkeys, sign_in_challenges, sign_in_codes
from app.db.passkeys import AddPasskeyParams
from app.db.sign_in_challenges import AddChallengeParams
from app.sign_in.codes import code_hash
from app.sign_in.session import start_session

CHALLENGE_LIFETIME = timedelta(minutes=5)
# A malformed credential can fail in the library's parsing before its checks.
REFUSED = (WebAuthnException, ValueError, KeyError, TypeError)


class SignInFailed(Exception):
    """A code, a challenge or a passkey that didn't work. Sent as 401."""


@dataclass
class Options:
    challenge_id: UUID
    options: dict[str, Any]


def redeem_code(database: Database, typed: str, moment: datetime) -> Options:
    """Spends a one-time code and returns the options for adding a passkey to its user."""
    with database.read() as connection:
        code = sign_in_codes.Querier(connection).find_code(code_hash=code_hash(typed))
    if code is None:
        raise SignInFailed
    with database.transaction(code.user_id, "redeem sign-in code") as connection:
        spent = sign_in_codes.Querier(connection).spend_code(
            id=code.id, user_id=code.user_id, used_at=moment
        )
        if spent is None:
            raise SignInFailed
        options = generate_registration_options(
            rp_id=PASSKEY_RP_ID,
            rp_name=APP_NAME,
            user_id=code.user_id.bytes,
            user_name=APP_NAME,
            timeout=int(CHALLENGE_LIFETIME.total_seconds() * 1000),
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
        )
        challenge_id = uuid4()
        sign_in_challenges.Querier(connection).add_challenge(
            AddChallengeParams(
                id=challenge_id,
                user_id=code.user_id,
                kind="add_passkey",
                challenge=bytes_to_base64url(options.challenge),
                expires_at=moment + CHALLENGE_LIFETIME,
            )
        )
    return Options(challenge_id, json.loads(options_to_json(options)))


def add_passkey(
    database: Database, challenge_id: UUID, credential: dict[str, Any], moment: datetime
) -> str:
    """Keeps the passkey the browser made for a redeemed code, and starts a session for its
    user. Returns the session's token."""
    with database.transaction(None, "add passkey") as connection:
        taken = sign_in_challenges.Querier(connection).take_challenge(
            id=challenge_id, kind="add_passkey"
        )
    if taken is None or taken.user_id is None or moment >= taken.expires_at:
        raise SignInFailed
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(taken.challenge),
            expected_rp_id=PASSKEY_RP_ID,
            expected_origin=APP_ORIGIN,
            require_user_verification=True,
        )
    except REFUSED as error:
        raise SignInFailed from error
    with database.transaction(taken.user_id, "add passkey") as connection:
        passkeys.Querier(connection).add_passkey(
            AddPasskeyParams(
                id=uuid4(),
                user_id=taken.user_id,
                credential_id=bytes_to_base64url(verified.credential_id),
                public_key=bytes_to_base64url(verified.credential_public_key),
                sign_count=verified.sign_count,
            )
        )
        return start_session(connection, taken.user_id, moment)
