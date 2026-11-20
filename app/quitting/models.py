"""A quitting goal's daily record, as the API sends and accepts it."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas import ApiModel

UrgeLevel = Literal["low", "some", "strong"]


class QuitDay(ApiModel):
    """One day of a quitting goal's record. Empty means unknown: no answer is never a slip."""

    goal_id: UUID
    day: date
    held: bool | None = Field(description="Yes or no for the day; empty when not answered.")
    urge: UrgeLevel | None = Field(description="How strong the urge was; empty when not rated.")


class QuitAnswer(ApiModel):
    held: bool


class UrgeRating(ApiModel):
    level: UrgeLevel
