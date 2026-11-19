"""Opening a week: what fills its bank (spec `week-turnover`). Runs inside the caller's
transaction, and takes the moment as an argument: nothing here reads the clock."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from uuid import UUID, uuid4

from sqlalchemy import Connection, text

from app.db import goals, models, recurring_items, tasks, turnover, users, weekly_targets
from app.db.users import GetUserRow
from app.planner import place_new_work
from app.tasks.rules import add_row, set_outcome
from app.turnover.due import Slot, goal_slots, item_slots
from app.turnover.endings import ending_for, item_of, schedule_of
from app.users import lock_user
from app.weeks import current_week

# The hour next week opens on Sunday (ADR-009), by the phone's clock.
OPENS_AT = time(18, 0)


@dataclass(frozen=True)
class Due:
    """What the weeks are due, from the user's two markers and the moment."""

    close: bool
    open_current: bool
    open_next: bool

    def __bool__(self) -> bool:
        return self.close or self.open_current or self.open_next


def what_is_due(owner: GetUserRow, now: datetime) -> Due:
    current = current_week(now.date(), owner.closed_through_week)
    planned = owner.planned_through_week
    opens_at = datetime.combine(current + timedelta(days=6), OPENS_AT, tzinfo=now.tzinfo)
    closed = owner.closed_through_week
    return Due(
        close=closed is None or closed < current - timedelta(weeks=1),
        open_current=planned is None or planned < current,
        open_next=now >= opens_at and (planned is None or planned <= current),
    )


def catch_up(connection: Connection, user_id: UUID, now: datetime) -> bool:
    """Brings the weeks up to date: opens the current week if it isn't open, and next week
    from 6 p.m. on Sunday. Returns whether it did anything. Safe to run twice."""
    owner = lock_user(connection, user_id)
    due = what_is_due(owner, now)
    if not due:
        return False
    current = current_week(now.date(), owner.closed_through_week)
    if due.close:
        last = current - timedelta(weeks=1)
        close_weeks(connection, user_id, last, current, owner.closed_through_week)
        set_action(connection, "open week")
        mark_closed(connection, user_id, last)
    if due.open_current:
        open_week(connection, user_id, current, now.date())
    if due.open_next:
        open_week(connection, user_id, current + timedelta(weeks=1), now.date())
    return True


SET_ACTION = text("select set_config('app.action', :action, true)")
NEVER = date(1, 1, 1)


def set_action(connection: Connection, action: str) -> None:
    """Names what the audit log records for the rest of this transaction."""
    connection.execute(SET_ACTION, {"action": action})


def mark_closed(connection: Connection, user_id: UUID, week: date) -> None:
    owner = users.Querier(connection).get_user(id=user_id)
    assert owner is not None
    if owner.closed_through_week is None or owner.closed_through_week < week:
        users.Querier(connection).set_closed_through_week(id=user_id, closed_through_week=week)


def close_weeks(
    connection: Connection, user_id: UUID, through: date, carry_to: date, after: date | None
) -> None:
    """Closes every week up to `through` that hasn't been closed, oldest first. Each unfinished
    row gets its ending: it rolls over into `carry_to`'s bank, or lapses and closes its task.
    A week with no rows has nothing to close. A set-aside generated task ends with its week or
    period and its row keeps saying set aside; one added by hand waits."""
    queries = turnover.Querier(connection)
    for row in queries.list_rows_to_close(user_id=user_id, through=through, after=after or NEVER):
        task = tasks.Querier(connection).get_task(id=row.task_id, user_id=user_id)
        assert task is not None
        ends = ending_for(connection, user_id, task, row.week)
        if row.outcome is None:
            if ends == "rolls_over":
                set_outcome(connection, user_id, row, "rolled_over")
                add_row(connection, user_id, row.task_id, carry_to)
            else:
                set_outcome(connection, user_id, row, "lapsed")
                tasks.Querier(connection).set_task_closed(
                    id=row.task_id, user_id=user_id, state="lapsed"
                )
        elif task.origin == "by_hand":
            continue
        else:
            item = item_of(connection, user_id, task)
            if ends == "rolls_over" and item is not None and item.schedule_kind == "flexible":
                add_row(connection, user_id, row.task_id, carry_to, outcome="set_aside")
            else:
                tasks.Querier(connection).set_task_closed(
                    id=row.task_id, user_id=user_id, state="lapsed"
                )


def open_week(connection: Connection, user_id: UUID, week: date, today: date) -> list[UUID]:
    """Fills a week's bank: the sessions of each active goal's target, the recurring tasks due
    in it, and open tasks now due. Makes only what's missing, then hands the new tasks to the
    planner and marks the week opened."""
    made: list[UUID] = []
    existing = existing_slots(connection, user_id, week)
    for goal, sessions in active_goals(connection, user_id, week):
        first_day = max(goal.start_date, today)
        for slot in goal_slots(sessions, week, first_day):
            if (goal.id, None, *slot) not in existing:
                made.append(
                    add_generated(connection, user_id, week, goal.label, goal.id, None, slot)
                )
    for item in recurring_items.Querier(connection).list_recurring_items(user_id=user_id):
        if not item.active:
            continue
        schedule = schedule_of(item)
        for slot in item_slots(schedule, week, max(item.starts_on, today)):
            if (None, item.id, *slot) not in existing:
                made.append(
                    add_generated(connection, user_id, week, item.name, None, item.id, slot)
                )
    for due in turnover.Querier(connection).list_due_tasks_without_rows(
        user_id=user_id, due_date=week + timedelta(days=6)
    ):
        add_row(connection, user_id, due, week)
    mark_opened(connection, user_id, week)
    place_new_work(connection, user_id, made, max(today, week))
    return made


def existing_slots(
    connection: Connection, user_id: UUID, week: date
) -> set[tuple[UUID | None, UUID | None, date, int]]:
    # A month's period starts up to five weeks before the week.
    rows = turnover.Querier(connection).list_generated_slots(
        user_id=user_id, period_start=week - timedelta(weeks=6)
    )
    return {
        (row.goal_id, row.recurring_item_id, row.period_start, row.number)
        for row in rows
        if row.period_start is not None and row.number is not None
    }


def active_goals(
    connection: Connection, user_id: UUID, week: date
) -> list[tuple[models.Goal, int]]:
    targets = {
        target.goal_id: target.sessions
        for target in weekly_targets.Querier(connection).weekly_targets_for(
            user_id=user_id, effective_from=week
        )
    }
    return [
        (goal, targets[goal.id])
        for goal in goals.Querier(connection).list_goals(user_id=user_id)
        if goal.type == "building" and goal.status == "active" and goal.id in targets
    ]


def add_generated(
    connection: Connection,
    user_id: UUID,
    week: date,
    title: str,
    goal_id: UUID | None,
    item_id: UUID | None,
    slot: Slot,
) -> UUID:
    task = turnover.Querier(connection).add_generated_task(
        turnover.AddGeneratedTaskParams(
            id=uuid4(),
            user_id=user_id,
            title=title,
            origin="weekly_target" if goal_id is not None else "recurring_item",
            goal_id=goal_id,
            recurring_item_id=item_id,
            period_start=slot[0],
            number=slot[1],
        )
    )
    assert task is not None
    add_row(connection, user_id, task.id, week)
    return task.id


def mark_opened(connection: Connection, user_id: UUID, week: date) -> None:
    owner = users.Querier(connection).get_user(id=user_id)
    assert owner is not None
    if owner.planned_through_week is None or owner.planned_through_week < week:
        users.Querier(connection).set_planned_through_week(id=user_id, planned_through_week=week)
