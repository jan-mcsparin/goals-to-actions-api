from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, Field, StringConstraints

from app.db import models as rows
from app.goals.models import Goal, Progress, WeekProgress
from app.quitting.models import QuitRecord
from app.schemas import ApiModel, NoNul
from app.tasks.models import Task

MilestoneStatus = Literal["upcoming", "hit", "notYet"]

STATUS_IN_JSON: dict[str, MilestoneStatus] = {
    "upcoming": "upcoming",
    "hit": "hit",
    "not_yet": "notYet",
}

Line = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500), NoNul]


class Milestone(ApiModel):
    id: UUID
    position: int
    measurable_line: str
    target_date: date | None
    status: MilestoneStatus
    result: str | None = Field(
        description="Its latest check-in's result, hit or not yet. Empty while it's upcoming."
    )

    @classmethod
    def from_row(cls, row: rows.Milestone, result: str | None) -> Milestone:
        return cls(
            id=row.id,
            position=row.position,
            measurable_line=row.measurable_line,
            target_date=row.target_date,
            status=STATUS_IN_JSON[row.status],
            result=result,
        )


class LatestResult(ApiModel):
    """The goal's most recent check-in with a result, shown as "Latest"."""

    result: str
    checked_in_on: date


class AspirationRef(ApiModel):
    """The aspiration a goal is under, named on its page."""

    id: UUID
    name: str


class GoalPage(ApiModel):
    """Everything a goal's page reads."""

    goal: Goal
    aspiration: AspirationRef | None
    milestones: list[Milestone] = Field(description="In the order they're checked in.")
    progress: Progress = Field(description="Milestones hit, or a one-off goal's steps done.")
    week_progress: WeekProgress | None = Field(
        description="This week against its target. Empty without a target this week."
    )
    steps: list[Task] = Field(
        description="A one-off goal's tasks, done and not, in the order added; dropped ones "
        "left out. Empty for other goals."
    )
    latest: LatestResult | None
    quit_record: QuitRecord | None = Field(
        description="A quitting goal's record; empty for others."
    )


class NewMilestone(ApiModel):
    goal_id: UUID
    measurable_line: Line
    target_date: date | None = None


class MilestoneEdit(ApiModel):
    """Sent whole. Moving or adjusting a "not yet" is an edit: it makes it upcoming again."""

    measurable_line: Line
    target_date: date | None = None


class MilestoneOrder(ApiModel):
    """Every milestone of the goal, first to be checked in first."""

    ids: Annotated[list[UUID], Field(max_length=500)]


def empty_when_blank(text: str | None) -> str | None:
    return text or None


class NewCheckIn(ApiModel):
    """A check-in against Next: the first milestone that isn't hit, or the goal's own line
    (`milestoneId` empty) once every milestone is hit. Dated today where the phone is."""

    goal_id: UUID
    milestone_id: UUID | None
    outcome: Literal["hit", "notYet"]
    result: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, max_length=500),
        NoNul,
        AfterValidator(empty_when_blank),
    ] = None
