"""The goal's page: the read that `getGoal` and every milestone write return."""

from datetime import date
from uuid import UUID

from sqlalchemy import Connection

from app.db import check_ins, goals, milestones
from app.errors import NotFound
from app.goals.models import Goal
from app.goals.rules import latest_target
from app.milestones.models import GoalPage, LatestResult, Milestone, Progress


def goal_page(connection: Connection, user_id: UUID, goal_id: UUID, today: date) -> GoalPage:
    goal = goals.Querier(connection).get_goal(id=goal_id, user_id=user_id)
    if goal is None:
        raise NotFound
    rows = list(milestones.Querier(connection).list_milestones(goal_id=goal_id, user_id=user_id))
    latest = check_ins.Querier(connection).latest_result(goal_id=goal_id, user_id=user_id)
    hit = sum(row.status == "hit" for row in rows) + (goal.status == "reached")
    return GoalPage(
        goal=Goal.from_row(goal, latest_target(connection, user_id, goal_id), today),
        milestones=[Milestone.from_row(row) for row in rows],
        progress=Progress(hit=hit, of=len(rows) + 1),
        latest=None
        if latest is None or latest.result is None
        else LatestResult(result=latest.result, checked_in_on=latest.checked_in_on),
    )
