from datetime import date, datetime
from datetime import time as Time
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints

from app.db.tasks import (
    GetTaskViewRow,
    ListDatedTasksRow,
    ListStepsRow,
    ListUpcomingRow,
    ListWeekTasksRow,
)
from app.goals.models import Label, WeeklyTarget, WeekProgress
from app.quitting.models import WeekQuitGoal
from app.schemas import ApiModel
from app.turnover.endings import ending_of
from app.weeks import WeekStatus

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
WeekOutcome = Literal["rolledOver", "lapsed"]
OUTCOME_IN_JSON: dict[str, WeekOutcome] = {"rolled_over": "rolledOver", "lapsed": "lapsed"}
# Recurring items whose tasks are due on a set day.
FIXED_KINDS = ("weekly", "monthly")
# How many rollovers since the last answer make a task worth asking about.
ASK_AFTER_ROLLOVERS = 2

TaskRow = GetTaskViewRow | ListWeekTasksRow | ListStepsRow | ListUpcomingRow | ListDatedTasksRow

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


class PlanAspiration(ApiModel):
    """The aspiration a task is under, so the phone can order and label the plan from the week
    read alone."""

    id: UUID
    name: str
    position: int | None = Field(description="Its priority; empty once it's retired.")

    @classmethod
    def from_columns(
        cls, aspiration_id: UUID | None, name: str | None, position: int | None
    ) -> PlanAspiration | None:
        if aspiration_id is None or name is None:
            return None
        return cls(id=aspiration_id, name=name, position=position)


class Task(ApiModel):
    id: UUID
    title: str
    origin: TaskOrigin
    state: TaskState
    goal_id: UUID | None
    goal_label: str | None
    aspiration: PlanAspiration | None = Field(
        description=(
            "Its goal's aspiration, or for a recurring item's task with no goal, the item's."
            " Empty when it's under none."
        )
    )
    recurring_item_id: UUID | None
    fixed_day: bool = Field(
        description="From a weekly or monthly recurring item, in the week it was due: it doesn't "
        "go to the bank, and moves only within its week. One that carried over is placed like "
        "any task."
    )
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
    week_outcome: WeekOutcome | None = Field(
        description="How the week read's row ended for this task: it rolled over, or lapsed. "
        "Empty for a row in play or done, and in every other read and write. A task that "
        "rolled over and was checked off late reads `rolledOver` here and `done` in `state`.",
    )

    @classmethod
    def from_row(cls, row: TaskRow) -> Task:
        return cls(
            id=row.id,
            title=row.title,
            origin=ORIGIN_IN_JSON[row.origin],
            state=STATE_IN_JSON[row.state],
            goal_id=row.goal_id,
            goal_label=row.goal_label,
            aspiration=PlanAspiration.from_columns(
                row.aspiration_id, row.aspiration_name, row.aspiration_position
            ),
            recurring_item_id=row.recurring_item_id,
            fixed_day=is_fixed_day(row.item_kind, row.carried_over),
            due_date=row.due_date,
            time_of_day=TimeOfDay.from_columns(row.time_kind, row.time_of_day),
            value_logged=None if row.value_logged is None else float(row.value_logged),
            completed_at=row.completed_at,
            completed_on=row.completed_on,
            week=row.week,
            planned_day=row.planned_day,
            placed_by_hand=bool(row.placed_by_hand),
            carried_over=row.carried_over,
            at_close=None if row.week_outcome in OUTCOME_IN_JSON else at_close(row),
            still_matters=still_matters(row),
            week_outcome=OUTCOME_IN_JSON.get(row.week_outcome or ""),
        )


def at_close(
    row: TaskRow,
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


def is_fixed_day(item_kind: str | None, carried_over: int) -> bool:
    """From a weekly or monthly item, in the week it was due: it doesn't go to the bank, and
    moves only within its week."""
    return item_kind in FIXED_KINDS and carried_over == 0


def still_matters(
    row: TaskRow,
) -> bool:
    asked_about = row.origin == "by_hand" or row.item_kind in FIXED_KINDS
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
        description="A day from today on, in this week or a later one. The task is placed "
        "there by hand. A day before today goes to the current week's bank.",
    )


class WeekGoal(ApiModel):
    """A bar on Week: a goal's target that week and how far along it is."""

    id: UUID
    label: str
    aspiration: PlanAspiration | None = Field(
        description="The aspiration it's under. Empty when it's under none."
    )
    weekly_target: WeeklyTarget
    progress: WeekProgress


class WeekCounts(ApiModel):
    """How full a week is (product rule 11): its tasks by origin. Actual for a week that has
    opened (every task the read returns); expected for one that hasn't (what opening it would
    bring). Check-ins, deadlines and quit days are never counted."""

    goal_sessions: int = Field(description="Tasks a goal's weekly target made.")
    goals: int = Field(description="How many goals the goal sessions are for.")
    upkeep: int = Field(description="Tasks a recurring item made.")
    added: int = Field(description="Tasks added by hand, a one-off goal's steps included.")


class DayCounts(ApiModel):
    """A day's tasks by origin, as `WeekCounts` counts them."""

    goal_sessions: int
    upkeep: int
    added: int


class DayMark(ApiModel):
    """A day's cap and whether it's reached: a guide shown on Week, never enforced (ADR-013)."""

    day: date
    cap: int = Field(description="Tasks a day holds at the person's intensity: 3, 4 or 6.")
    full: bool = Field(
        description="The day holds at least `cap` of the tasks the week read returns: open or "
        "done, and in a closed week also rolled over or lapsed."
    )
    counts: DayCounts | None = Field(
        description="The day's tasks by origin. Empty for a week that hasn't opened."
    )


class Occurrence(ApiModel):
    """A fixed-day recurring item due in a week that hasn't opened: worked out from its
    schedule, not stored."""

    recurring_item_id: UUID
    title: str
    day: date


class CheckInDate(ApiModel):
    """A milestone dated in the week that isn't hit yet, under an active goal."""

    goal_id: UUID
    goal_label: str
    milestone_id: UUID
    position: int
    of: int = Field(
        description="Out of the goal's milestones and the goal, as its page counts them: "
        '"Milestone 3 of 4".'
    )
    day: date


class GoalDeadline(ApiModel):
    """An active goal's deadline in the week."""

    goal_id: UUID
    goal_label: str
    day: date


class Week(ApiModel):
    """The plan read (ADR-010). The phone keeps it and draws Today, any day and the bank
    from it."""

    week: date
    status: WeekStatus = Field(
        description="`closed` before the current week, `open` for the current week and next "
        "week once open, `notOpen` for every later week."
    )
    is_current: bool
    next_week_open: bool = Field(description="Next week has been opened (from Sunday evening).")
    first_week: date | None = Field(
        description="The Monday of the earliest week with any row, whatever its outcome: how "
        "far back Week can go. Empty when there are none."
    )
    tasks: list[Task] = Field(
        description="On a day, then in the bank: in play or done, and in a closed week also "
        "rolled over or lapsed (`weekOutcome`). A week that hasn't opened has only the tasks "
        "placed on it by hand. Set-aside and dropped rows aren't shown."
    )
    goals: list[WeekGoal] = Field(
        description="An open week: every active building goal with a target that week. A "
        "closed week: every goal with a target and a session row that week, whatever its "
        "status now. A week that hasn't opened: none."
    )
    days: list[DayMark] = Field(description="Monday to Sunday, each with the full-day mark.")
    counts: WeekCounts
    occurrences: list[Occurrence] = Field(
        description="A week that hasn't opened: each fixed-day recurring item due in it. "
        "Empty for every other week."
    )
    check_ins: list[CheckInDate] = Field(
        description="Milestones dated in the week that aren't hit yet, under active goals, by "
        "day. Never counted."
    )
    deadlines: list[GoalDeadline] = Field(
        description="Active goals whose deadline falls in the week, by day. Never counted."
    )
    quitting_goals: list[WeekQuitGoal] = Field(
        description="Every active quitting goal started by the week's end, with its days."
    )
    next_up: Task | None = Field(
        description="The current week's read only: the next open task added by hand set to a "
        "day, or else due, after today and through Coming up's last week. Earliest by its day, "
        "then time. Empty in every other week's read, and when there's none."
    )


class ComingUpWeek(ApiModel):
    """A week on Coming up (spec `coming-up`)."""

    week: date
    status: Literal["open", "notOpen"] = Field(
        description="The first week is `open` from Sunday evening; the rest are `notOpen`."
    )
    counts: WeekCounts = Field(description="The same numbers `getWeek` gives for the week.")
    tasks: list[Task] = Field(
        description="Open tasks added by hand, under no goal or an active one, set to a day in "
        "the week or else due in it; by day, then time."
    )
    check_ins: list[CheckInDate] = Field(description="As `getWeek`'s.")
    deadlines: list[GoalDeadline] = Field(description="As `getWeek`'s.")


class ComingUp(ApiModel):
    weeks: list[ComingUpWeek] = Field(
        description="The 12 weeks after the current one, oldest first."
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
    day: date = Field(
        description="A day from today on. A task added by hand can go to another week; a "
        "generated one stays in its own."
    )


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
