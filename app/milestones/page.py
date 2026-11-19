"""The goal's page: the read that `getGoal` and every milestone write return."""

from datetime import date
from uuid import UUID

from sqlalchemy import Connection

from app.db import aspirations, check_ins, goals, milestones
from app.errors import NotFound
from app.goals.models import Goal, Progress
from app.goals.rules import latest_target
from app.milestones.models import AspirationRef, GoalPage, LatestResult, Milestone


def goal_page(connection: Connection, user_id: UUID, goal_id: UUID, today: date) -> GoalPage:
    goal = goals.Querier(connection).get_goal(id=goal_id, user_id=user_id)
    if goal is None:
        raise NotFound
    rows = list(milestones.Querier(connection).list_milestones(goal_id=goal_id, user_id=user_id))
    results = {
        row.milestone_id: row.result
        for row in check_ins.Querier(connection).hit_results(goal_id=goal_id, user_id=user_id)
    }
    latest = check_ins.Querier(connection).latest_result(goal_id=goal_id, user_id=user_id)
    hit = sum(row.status == "hit" for row in rows)
    return GoalPage(
        goal=Goal.from_row(goal, latest_target(connection, user_id, goal_id), today),
        aspiration=aspiration_of(connection, user_id, goal.aspiration_id),
        milestones=[
            Milestone.from_row(row, results.get(row.id) if row.status == "hit" else None)
            for row in rows
        ],
        progress=Progress.counted(len(rows), hit, goal.status),
        latest=None
        if latest is None or latest.result is None
        else LatestResult(result=latest.result, checked_in_on=latest.checked_in_on),
    )


def aspiration_of(
    connection: Connection, user_id: UUID, aspiration_id: UUID | None
) -> AspirationRef | None:
    if aspiration_id is None:
        return None
    row = aspirations.Querier(connection).get_aspiration(id=aspiration_id, user_id=user_id)
    return None if row is None else AspirationRef(id=row.id, name=row.name)
