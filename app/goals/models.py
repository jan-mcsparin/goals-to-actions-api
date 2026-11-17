from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AfterValidator, Field, StringConstraints, model_validator

from app.db import models as rows
from app.schemas import ApiModel, NoNul

GoalType = Literal["building", "quitting", "oneOff"]
GoalStatus = Literal["active", "paused", "reached", "ended"]

# The database spells two-word values in snake_case, JSON in camelCase.
TYPE_IN_DATABASE: dict[GoalType, str] = {
    "building": "building",
    "quitting": "quitting",
    "oneOff": "one_off",
}
TYPE_IN_JSON: dict[str, GoalType] = {stored: sent for sent, stored in TYPE_IN_DATABASE.items()}


def empty_when_blank(text: str | None) -> str | None:
    return text or None


Label = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200), NoNul
]
Line = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500), NoNul]
Baseline = Annotated[
    str | None,
    StringConstraints(strip_whitespace=True, max_length=500),
    NoNul,
    AfterValidator(empty_when_blank),
]


class WeeklyTarget(ApiModel):
    kind: Literal["count", "amount"]
    sessions: int
    amount: float | None
    unit: str
    effective_from: date

    @classmethod
    def from_row(cls, row: rows.WeeklyTarget) -> WeeklyTarget:
        return cls(
            kind=row.kind,
            sessions=row.sessions,
            amount=None if row.amount is None else float(row.amount),
            unit=row.unit,
            effective_from=row.effective_from,
        )


class Goal(ApiModel):
    id: UUID
    aspiration_id: UUID | None
    type: GoalType
    label: str
    measurable_line: str
    baseline: str | None
    status: GoalStatus
    start_date: date
    deadline: date | None
    ended_on: date | None
    slipped: bool = Field(description="Active, with its deadline before today.")
    weekly_target: WeeklyTarget | None = Field(
        description="The latest target. Its effectiveFrom is after this week when a change "
        "waits for next week. Empty for quitting and one-off goals."
    )
    created_at: datetime

    @classmethod
    def from_row(cls, row: rows.Goal, target: rows.WeeklyTarget | None, today: date) -> Goal:
        return cls(
            id=row.id,
            aspiration_id=row.aspiration_id,
            type=TYPE_IN_JSON[row.type],
            label=row.label,
            measurable_line=row.measurable_line,
            baseline=row.baseline,
            status=row.status,
            start_date=row.start_date,
            deadline=row.deadline,
            ended_on=row.ended_on,
            slipped=row.status == "active" and row.deadline is not None and row.deadline < today,
            weekly_target=None if target is None else WeeklyTarget.from_row(target),
            created_at=row.created_at,
        )


class GoalList(ApiModel):
    goals: list[Goal]


class WeeklyTargetInput(ApiModel):
    """A count ("3 lifting sessions") or an amount ("25 miles over 4 runs")."""

    kind: Literal["count", "amount"]
    sessions: Annotated[int, Field(ge=1, le=14)]
    amount: Annotated[float | None, Field(gt=0, le=1_000_000)] = None
    unit: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100), NoNul
    ]

    @model_validator(mode="after")
    def amount_matches_kind(self) -> Self:
        if (self.kind == "amount") != (self.amount is not None):
            raise ValueError("An amount target needs an amount, and a count target has none.")
        return self

    def stored_amount(self) -> Decimal | None:
        return None if self.amount is None else Decimal(str(self.amount))


class NewGoal(ApiModel):
    """A goal as first made. A building goal comes with its first weekly target."""

    type: GoalType
    label: Label
    measurable_line: Line
    baseline: Baseline = None
    aspiration_id: UUID | None = None
    start_date: date | None = Field(default=None, description="Today when left out.")
    deadline: date | None = None
    weekly_target: WeeklyTargetInput | None = None

    @model_validator(mode="after")
    def follows_the_rules(self) -> Self:
        if (self.type == "building") != (self.weekly_target is not None):
            raise ValueError("A building goal needs a weekly target, and other goals have none.")
        if self.start_date and self.deadline and self.deadline < self.start_date:
            raise ValueError("A deadline can't be before the start date.")
        return self


class GoalEdit(ApiModel):
    """Sent whole on every edit. A goal's type and start date don't change."""

    label: Label
    measurable_line: Line
    baseline: Baseline = None
    aspiration_id: UUID | None = None
    deadline: date | None = None
