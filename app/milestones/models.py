from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints

from app.db import models as rows
from app.goals.models import Goal
from app.schemas import ApiModel, NoNul

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

    @classmethod
    def from_row(cls, row: rows.Milestone) -> Milestone:
        return cls(
            id=row.id,
            position=row.position,
            measurable_line=row.measurable_line,
            target_date=row.target_date,
            status=STATUS_IN_JSON[row.status],
        )


class Progress(ApiModel):
    """ "2 of 6": the goal's milestones plus one for the goal, which counts once reached."""

    hit: int
    of: int


class LatestResult(ApiModel):
    """The goal's most recent check-in with a result, shown as "Latest"."""

    result: str
    checked_in_on: date


class GoalPage(ApiModel):
    """Everything a goal's page reads."""

    goal: Goal
    milestones: list[Milestone] = Field(description="In the order they're checked in.")
    progress: Progress
    latest: LatestResult | None


class NewMilestone(ApiModel):
    goal_id: UUID
    measurable_line: Line
    target_date: date | None = None


class MilestoneEdit(ApiModel):
    """Sent whole. Moving or adjusting a "not yet" is an edit: it makes it upcoming again."""

    measurable_line: Line
    target_date: date | None = None
