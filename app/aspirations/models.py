from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, StringConstraints

from app.db import models as rows
from app.schemas import ApiModel


class Aspiration(ApiModel):
    id: UUID
    name: str
    why: str | None
    status: Literal["active", "retired"]
    position: int | None
    retired_on: date | None
    created_at: datetime

    @classmethod
    def from_row(cls, row: rows.Aspiration) -> Aspiration:
        return cls.model_validate(row, from_attributes=True)


class AspirationList(ApiModel):
    aspirations: list[Aspiration]

    @classmethod
    def from_rows(cls, aspirations: list[rows.Aspiration]) -> AspirationList:
        return cls(aspirations=[Aspiration.from_row(row) for row in aspirations])


def empty_when_blank(why: str | None) -> str | None:
    return why or None


class AspirationInput(ApiModel):
    """What the person types. Sent whole on create and on every edit."""

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    why: Annotated[
        str | None, StringConstraints(strip_whitespace=True), AfterValidator(empty_when_blank)
    ] = None
