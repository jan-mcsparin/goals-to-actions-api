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


class QuitRecord(ApiModel):
    """A quitting goal's recent days and its run, worked out on every read."""

    days: list[QuitDay] = Field(
        description="The last 28 days up to today, from the goal's start at the earliest, "
        "newest first."
    )
    held_run: int = Field(description="Days held since the last no, or since the start.")
    unknown_in_run: int = Field(
        description="Days before today since then with no answer yet. They can still be answered."
    )


class WeekQuitGoal(ApiModel):
    """An active quitting goal on the week read, so the phone can show and answer its days
    offline."""

    id: UUID
    label: str
    days: list[QuitDay] = Field(description="Each day of the week from the goal's start.")
