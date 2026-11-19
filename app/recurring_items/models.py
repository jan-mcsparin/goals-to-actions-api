from dataclasses import dataclass
from datetime import date, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from app.db import models as rows
from app.schemas import ApiModel, NoNul

Weekday = Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
# Stored as ISO numbers: Monday is 1.
WEEKDAYS: tuple[Weekday, ...] = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

Period = Literal["week", "twoWeeks", "month"]
PERIOD_IN_DATABASE: dict[Period, str] = {"week": "week", "twoWeeks": "two_weeks", "month": "month"}
PERIOD_IN_JSON: dict[str, Period] = {stored: sent for sent, stored in PERIOD_IN_DATABASE.items()}


class WeeklySchedule(ApiModel):
    """Every week on a weekday: "Every Tuesday"."""

    kind: Literal["weekly"]
    weekday: Weekday


class MonthlySchedule(ApiModel):
    """Every month on a day, up to the 28th so every month has it: "Monthly on the 1st"."""

    kind: Literal["monthly"]
    day_of_month: Annotated[int, Field(ge=1, le=28)]


class FlexibleSchedule(ApiModel):
    """Some time in each period: 1 to 6 times a week, or once every two weeks or a month."""

    kind: Literal["flexible"]
    times: Annotated[int, Field(ge=1, le=6)]
    period: Period

    @model_validator(mode="after")
    def once_in_a_longer_period(self) -> Self:
        if self.period != "week" and self.times != 1:
            raise ValueError("Every two weeks and every month are once.")
        return self


Schedule = Annotated[
    WeeklySchedule | MonthlySchedule | FlexibleSchedule, Field(discriminator="kind")
]


def schedule_from_row(row: rows.RecurringItem) -> Schedule:
    if row.schedule_kind == "weekly":
        assert row.weekday is not None
        return WeeklySchedule(kind="weekly", weekday=WEEKDAYS[row.weekday - 1])
    if row.schedule_kind == "monthly":
        assert row.day_of_month is not None
        return MonthlySchedule(kind="monthly", day_of_month=row.day_of_month)
    assert row.times is not None and row.period is not None
    return FlexibleSchedule(kind="flexible", times=row.times, period=PERIOD_IN_JSON[row.period])


@dataclass(frozen=True)
class StoredSchedule:
    """The schedule as the table's columns, every one but its kind's left empty."""

    schedule_kind: str
    weekday: int | None = None
    day_of_month: int | None = None
    times: int | None = None
    period: str | None = None

    @classmethod
    def of(cls, schedule: Schedule) -> StoredSchedule:
        match schedule:
            case WeeklySchedule():
                return cls(schedule_kind="weekly", weekday=WEEKDAYS.index(schedule.weekday) + 1)
            case MonthlySchedule():
                return cls(schedule_kind="monthly", day_of_month=schedule.day_of_month)
            case FlexibleSchedule():
                return cls(
                    schedule_kind="flexible",
                    times=schedule.times,
                    period=PERIOD_IN_DATABASE[schedule.period],
                )


class RecurringItem(ApiModel):
    id: UUID
    name: str
    aspiration_id: UUID | None = Field(
        description="Planned as goal work under this aspiration. Empty: maintenance, in Keep "
        "life running."
    )
    from_goal_id: UUID | None = Field(description="The reached goal whose practice this keeps.")
    schedule: Schedule
    starts_on: date = Field(
        description="The first day it can be due. It also anchors a two-week period."
    )
    active: bool
    created_at: datetime

    @classmethod
    def from_row(cls, row: rows.RecurringItem) -> RecurringItem:
        return cls(
            id=row.id,
            name=row.name,
            aspiration_id=row.aspiration_id,
            from_goal_id=row.from_goal_id,
            schedule=schedule_from_row(row),
            starts_on=row.starts_on,
            active=row.active,
            created_at=row.created_at,
        )


class RecurringItemList(ApiModel):
    recurring_items: list[RecurringItem]


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200), NoNul]


class NewRecurringItem(ApiModel):
    name: Name
    aspiration_id: UUID | None = None
    from_goal_id: UUID | None = Field(
        default=None, description="Set when a reached goal's practice is kept going."
    )
    schedule: Schedule
    starts_on: date
