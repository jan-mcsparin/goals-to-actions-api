"""Every write in the API, sent twice, gives the same answer and leaves the same data
(spec `settings-sync`). This is what lets the phone's offline queue resend a write it isn't
sure arrived (ADR-004, ADR-010).

Each case arranges what its write needs and returns the request. The first send may change
things; the second must give the same status and body, and leave every row of the user's as
the first left it. `updated_at` is left out: it records when a row was last touched, not
what it holds."""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.config import FIXED_USER_ID
from tests.test_check_ins import check_in
from tests.test_goals import ZONE, create_goal, edit, lifting
from tests.test_milestones import add_milestone

Request = tuple[str, str, dict[str, Any] | None]
Arrange = Callable[[TestClient], Request]

FOUR_RUNS = {"kind": "amount", "sessions": 4, "amount": 25, "unit": "miles"}


def ok(response: Any) -> Any:
    assert response.status_code < 300, response.text
    return response.json() if response.content else None


def aspiration(client: TestClient, name: str = "Be healthy") -> str:
    return str(ok(client.put(f"/api/aspirations/{uuid4()}", json={"name": name}))["id"])


def goal(client: TestClient) -> str:
    return str(create_goal(client, lifting())["id"])


def goal_after(client: TestClient, action: str) -> str:
    goal_id = goal(client)
    ok(client.post(f"/api/goals/{goal_id}/{action}"))
    return goal_id


def milestone(client: TestClient, goal_id: str, line: str = "Bench 155") -> str:
    return str(ok(add_milestone(client, goal_id, line))["milestones"][-1]["id"])


# Aspirations


def create_aspiration(client: TestClient) -> Request:
    return "PUT", f"/api/aspirations/{uuid4()}", {"name": "Be healthy", "why": "Feel good"}


def update_aspiration(client: TestClient) -> Request:
    return "PATCH", f"/api/aspirations/{aspiration(client)}", {"name": "Be fit"}


def reorder_aspirations(client: TestClient) -> Request:
    first, second = aspiration(client, "First"), aspiration(client, "Second")
    return "POST", "/api/aspirations/reorder", {"ids": [second, first]}


def retire_aspiration(client: TestClient) -> Request:
    return "POST", f"/api/aspirations/{aspiration(client)}/retire", {"itsWork": "pause"}


def bring_back_aspiration(client: TestClient) -> Request:
    aspiration_id = aspiration(client)
    ok(client.post(f"/api/aspirations/{aspiration_id}/retire", json={"itsWork": "keep"}))
    return "POST", f"/api/aspirations/{aspiration_id}/bring-back", None


def delete_aspiration(client: TestClient) -> Request:
    aspiration(client, "Stays")
    return "DELETE", f"/api/aspirations/{aspiration(client)}", None


# Goals


def create_goal_request(client: TestClient) -> Request:
    return "PUT", f"/api/goals/{uuid4()}", lifting()


def update_goal(client: TestClient) -> Request:
    return "PATCH", f"/api/goals/{goal(client)}", edit()


def set_weekly_target(client: TestClient) -> Request:
    return "PUT", f"/api/goals/{goal(client)}/weekly-target", FOUR_RUNS


def pause_goal(client: TestClient) -> Request:
    return "POST", f"/api/goals/{goal(client)}/pause", None


def resume_goal(client: TestClient) -> Request:
    return "POST", f"/api/goals/{goal_after(client, 'pause')}/resume", None


def end_goal(client: TestClient) -> Request:
    return "POST", f"/api/goals/{goal(client)}/end", None


def mark_goal_reached(client: TestClient) -> Request:
    return "POST", f"/api/goals/{goal(client)}/mark-reached", None


def reopen_goal(client: TestClient) -> Request:
    return "POST", f"/api/goals/{goal_after(client, 'mark-reached')}/reopen", None


def go_again(client: TestClient) -> Request:
    return "POST", f"/api/goals/{goal_after(client, 'end')}/go-again", None


def delete_goal(client: TestClient) -> Request:
    goal_id = goal(client)
    milestone(client, goal_id)
    return "DELETE", f"/api/goals/{goal_id}", None


# Milestones and check-ins


def add_milestone_request(client: TestClient) -> Request:
    body = {"goalId": goal(client), "measurableLine": "Bench 155", "targetDate": None}
    return "PUT", f"/api/milestones/{uuid4()}", body


def update_milestone(client: TestClient) -> Request:
    milestone_id = milestone(client, goal(client))
    body = {"measurableLine": "Bench 165", "targetDate": None}
    return "PATCH", f"/api/milestones/{milestone_id}", body


def reorder_milestones(client: TestClient) -> Request:
    goal_id = goal(client)
    first, second = milestone(client, goal_id, "M1"), milestone(client, goal_id, "M2")
    return "POST", f"/api/goals/{goal_id}/milestones/reorder", {"ids": [second, first]}


def keep_milestone(client: TestClient) -> Request:
    goal_id = goal(client)
    milestone_id = milestone(client, goal_id)
    ok(check_in(client, goal_id, milestone_id, "notYet", "140"))
    return "POST", f"/api/milestones/{milestone_id}/keep", None


def delete_milestone(client: TestClient) -> Request:
    goal_id = goal(client)
    milestone(client, goal_id, "M1")
    second = milestone(client, goal_id, "M2")
    milestone(client, goal_id, "M3")
    return "DELETE", f"/api/milestones/{second}", None


def check_in_request(client: TestClient) -> Request:
    goal_id = goal(client)
    body = {
        "goalId": goal_id,
        "milestoneId": milestone(client, goal_id),
        "outcome": "hit",
        "result": "155",
    }
    return "PUT", f"/api/check-ins/{uuid4()}", body


CASES: dict[str, Arrange] = {
    "createAspiration": create_aspiration,
    "updateAspiration": update_aspiration,
    "reorderAspirations": reorder_aspirations,
    "retireAspiration": retire_aspiration,
    "bringBackAspiration": bring_back_aspiration,
    "deleteAspiration": delete_aspiration,
    "createGoal": create_goal_request,
    "updateGoal": update_goal,
    "setWeeklyTarget": set_weekly_target,
    "pauseGoal": pause_goal,
    "resumeGoal": resume_goal,
    "endGoal": end_goal,
    "markGoalReached": mark_goal_reached,
    "reopenGoal": reopen_goal,
    "goAgain": go_again,
    "deleteGoal": delete_goal,
    "addMilestone": add_milestone_request,
    "updateMilestone": update_milestone,
    "reorderMilestones": reorder_milestones,
    "keepMilestone": keep_milestone,
    "deleteMilestone": delete_milestone,
    "checkIn": check_in_request,
}


def user_tables(connection: Connection) -> list[str]:
    """Every table with an owner, but the audit log: that records each send, by design."""
    return list(
        connection.execute(
            text(
                "select table_name from information_schema.columns"
                " where table_schema = 'public' and column_name = 'user_id'"
                " and table_name != 'audit_log' order by table_name"
            )
        ).scalars()
    )


def snapshot(connection: Connection) -> dict[str, list[str]]:
    """Every row of the user's, every column but `updated_at`."""
    found: dict[str, list[str]] = {}
    for table, owner in [("users", "id"), *((t, "user_id") for t in user_tables(connection))]:
        rows = connection.execute(
            text(f"select * from {table} where {owner} = :user_id"),
            {"user_id": FIXED_USER_ID},
        ).mappings()
        found[table] = sorted(
            repr({k: v for k, v in row.items() if k != "updated_at"}) for row in rows
        )
    return found


@pytest.mark.parametrize("operation", CASES)
def test_a_write_sent_twice_gives_the_same_answer_and_data(
    operation: str, client: TestClient, connection: Connection
) -> None:
    client.headers["X-Time-Zone"] = ZONE
    method, path, body = CASES[operation](client)

    first = client.request(method, path, json=body)
    assert first.status_code < 300, first.text
    after_first = snapshot(connection)
    second = client.request(method, path, json=body)

    assert second.status_code == first.status_code, second.text
    assert second.content == first.content
    assert snapshot(connection) == after_first
