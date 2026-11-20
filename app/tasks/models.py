from datetime import date, datetime
from datetime import time as Time
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints

from app.db.tasks import GetTaskViewRow, ListStepsRow, ListUpcomingRow, ListWeekTasksRow
from app.goals.models import Label, WeeklyTarget, WeekProgress
from app.quitting.models import WeekQuitGoal
from app.schemas import ApiModel
from app.turnover.endings import ending_of

TaskOrigin = Literal["byHand", "weeklyTarget", "recurringItem"]
TaskState = Literal["open", "done", "dropped", "lapsed"]

ORIGIN_IN_JSON: dict[str, TaskOrigin] = {
    "by_hand": "byHand",
    "weekly_target": "weeklyTarget",
    "recurring_item": "recurringItem",
}

STATE_IN_JSON: dict[str, TaskState] = {
    "open": "open",
    "done": "done",
    "dropped": "dropped",
    "lapsed": "lapsed",
}

AtClose = Literal["carriesOver", "ends"]
# How many rollovers since the last answer make a task worth asking about.
ASK_AFTER_ROLLOVERS = 2

Clock = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]


class TimeOfDay(ApiModel):
    """ "By 6 p.m." or "at 6 p.m.", wherever the phone is."""

    kind: Literal["by", "at"]
    time: Clock = Field(description="HH:MM, 24-hour.")

    def stored(self) -> Time:
        return Time.fromisoformat(self.time)

    @classmethod
    def from_columns(cls, kind: str | None, at: Time | None) -> TimeOfDay | None:
        if kind is None or at is None:
            return None
        return cls(kind="by" if kind == "by" else "at", time=at.strftime("%H:%M"))


class Task(ApiModel):
    id: UUID
    title: str
    origin: TaskOrigin
    state: TaskState
    goal_id: UUID | None
    goal_label: str | None
    recurring_item_id: UUID | None
    due_date: date | None
    time_of_day: TimeOfDay | None
    value_logged: float | None
    completed_at: datetime | None
    completed_on: date | None
    week: date | None = Field(
        description="The week of its row in play, or of its done row. Empty while it waits "
        "(the upcoming list, a one-off goal's waiting steps) or is set aside."
    )
    planned_day: date | None = Field(description="Empty in the bank.")
    placed_by_hand: bool
    carried_over: int = Field(description="How many weeks it rolled over before this one.")
    at_close: AtClose | None = Field(
        description="What closing its week does to it if it's still unfinished: it carries "
        "over to next week's bank, or ends with the week. Empty when it's done, closed, set "
        "aside or has no row in play. The wrap-up sheet reads this."
    )
    still_matters: bool = Field(
        description='Ask "Still matter?": added by hand or a fixed-day recurring task, open, '
        "and rolled over twice since it was last answered."
    )

    @classmethod
    def from_row(
        cls, row: GetTaskViewRow | ListWeekTasksRow | ListStepsRow | ListUpcomingRow
    ) -> Task:
        return cls(
            id=row.id,
            title=row.title,
            origin=ORIGIN_IN_JSON[row.origin],
            state=STATE_IN_JSON[row.state],
            goal_id=row.goal_id,
            goal_label=row.goal_label,
            recurring_item_id=row.recurring_item_id,
            due_date=row.due_date,
            time_of_day=TimeOfDay.from_columns(row.time_kind, row.time_of_day),
            value_logged=None if row.value_logged is None else float(row.value_logged),
            completed_at=row.completed_at,
            completed_on=row.completed_on,
            week=row.week,
            planned_day=row.planned_day,
            placed_by_hand=bool(row.placed_by_hand),
            carried_over=row.carried_over,
            at_close=at_close(row),
            still_matters=still_matters(row),
        )


def at_close(
    row: GetTaskViewRow | ListWeekTasksRow | ListStepsRow | ListUpcomingRow,
) -> AtClose | None:
    """The same rule closing uses (`app.turnover.endings.ending_of`), so the sheet and the close
    can't disagree."""
    if row.state != "open" or row.week is None:
        return None
    rolls_over = (
        ending_of(row.origin, row.item_kind, row.item_period, row.period_start, row.week)
        == "rolls_over"
    )
    return "carriesOver" if rolls_over else "ends"


def still_matters(
    row: GetTaskViewRow | ListWeekTasksRow | ListStepsRow | ListUpcomingRow,
) -> bool:
    asked_about = row.origin == "by_hand" or row.item_kind in ("weekly", "monthly")
    return row.state == "open" and asked_about and row.rolled_since_answer >= ASK_AFTER_ROLLOVERS


class Upcoming(ApiModel):
    tasks: list[Task] = Field(description="Open tasks with a due date and no row yet, by due date.")


class NewTask(ApiModel):
    """A task added by hand. `day` is where the phone put it; with none, it goes to the bank."""

    title: Label
    goal_id: UUID | None = None
    due_date: date | None = None
    time_of_day: TimeOfDay | None = None
    day: date | None = Field(
        default=None,
        description="A day to put it on, placed by hand. A day no longer allowed (a past day, "
        "or one outside the open weeks) saves it in the current week's bank instead.",
    )


class WeekGoal(ApiModel):
    """A bar on Week: a goal's target that week and how far along it is."""

    id: UUID
    label: str
    weekly_target: WeeklyTarget
    progress: WeekProgress


class DayMark(ApiModel):
    """A day's cap and whether it's reached: a guide shown on Week, never enforced (ADR-013)."""

    day: date
    cap: int = Field(description="Tasks a day holds at the person's intensity: 3, 4 or 6.")
    full: bool = Field(description="The day holds at least `cap` tasks, open or done.")


class Week(ApiModel):
    """The plan read (ADR-010). The phone keeps it and draws Today, any day and the bank
    from it."""

    week: date
    is_current: bool
    next_week_open: bool = Field(description="Next week has been opened (from Sunday evening).")
    tasks: list[Task] = Field(
        description="On a day, then in the bank; with no outcome or done. Set-aside rows "
        "aren't shown."
    )
    goals: list[WeekGoal] = Field(
        description="Every active building goal with a target that week, and its progress."
    )
    days: list[DayMark] = Field(description="Monday to Sunday, each with the full-day mark.")
    quitting_goals: list[WeekQuitGoal] = Field(
        description="Every active quitting goal started by the week's end, with its days."
    )


class TaskEdit(ApiModel):
    """Sent whole on every edit. Where the task is doesn't change."""

    title: Label
    due_date: date | None = None
    time_of_day: TimeOfDay | None = None


class CheckOff(ApiModel):
    """What the phone saw when the task was checked off. Its day wins, even for a week that
    has since closed."""

    completed_at: AwareDatetime = Field(description="The moment, as the phone recorded it.")
    completed_on: date = Field(
        description="The day it counts for, as the phone saw it: 12:30 a.m. is the new day."
    )
    value_logged: Annotated[float | None, Field(ge=0, le=1_000_000)] = Field(
        default=None, description="Miles, minutes: counts towards an amount target."
    )

    def stored_value(self) -> Decimal | None:
        return None if self.value_logged is None else Decimal(str(self.value_logged))


class Placing(ApiModel):
    """Onto a day, placed by hand, in the week the change was made in."""

    week: date = Field(
        description="The week the change was made in. Refused once the task has left it."
    )
    day: date


class ToBank(ApiModel):
    week: date = Field(
        description="The week the change was made in. Refused once the task has left it."
    )


class KeepIt(ApiModel):
    answer: Literal["keep"]


class ScheduleIt(ApiModel):
    """Onto a day, placed by hand, as `placeTask` does."""

    answer: Literal["schedule"]
    week: date = Field(
        description="The week the change was made in. Refused once the task has left it."
    )
    day: date


class DropIt(ApiModel):
    answer: Literal["drop"]


StillMattersAnswer = Annotated[KeepIt | ScheduleIt | DropIt, Field(discriminator="answer")]


class Swap(ApiModel):
    """The task in the route goes to the bank; the bank task goes onto the day."""

    week: date = Field(
        description="The week the change was made in. Refused once either task has left it."
    )
    bank_task_id: UUID
    day: date


class Swapped(ApiModel):
    to_bank: Task
    placed: Task
