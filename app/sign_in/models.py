from typing import Annotated, Any
from uuid import UUID

from pydantic import Field

from app.schemas import ApiModel, NoNul


class RedeemCode(ApiModel):
    code: Annotated[str, Field(max_length=64), NoNul]


class PasskeyOptions(ApiModel):
    """What the browser's passkey functions take, as JSON, and the challenge to send back."""

    challenge_id: UUID
    options: dict[str, Any]


class SignedChallenge(ApiModel):
    """The browser's `PublicKeyCredential` as JSON, for the challenge it signed."""

    challenge_id: UUID
    credential: dict[str, Any]
