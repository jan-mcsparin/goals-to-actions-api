"""Every write in the API, sent twice, gives the same answer and leaves the same data
(spec `settings-sync`). This is what lets the phone's offline queue resend a write it isn't
sure arrived (ADR-004, ADR-010).

Each case arranges what its write needs and returns the request. The first send must change
something; the second must give the same status and body, and leave every row of the user's as
the first left it. `updated_at` is left out: it records when a row was last touched, not
what it holds. A last test fails for any write in the schema without a case."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.config import FIXED_USER_ID
from tests.conftest import FixedClock
from tests.test_at_close import add_rolled_rows
from tests.test_check_ins import check_in
from tests.test_check_off import done_on
from tests.test_close_week import W1, W2, W3, new_task
from tests.test_goals import ZONE, create_goal, edit, lifting, no_sugar, today
from tests.test_milestones import add_milestone
from tests.test_recurring_items import item
from tests.test_task_moves import this_week
from tests.test_wrap_up import SUNDAY_EVENING

Request = tuple[str, str, dict[str, Any] | None]


@dataclass
class Given:
    """What a case can arrange with. Most need only the client."""

    client: TestClient
    connection: Connection
    clock: FixedClock


Arrange = Callable[[Given], Request]

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


def create_aspiration(given: Given) -> Request:
    return "PUT", f"/api/aspirations/{uuid4()}", {"name": "Be healthy", "why": "Feel good"}


def update_aspiration(given: Given) -> Request:
    return "PATCH", f"/api/aspirations/{aspiration(given.client)}", {"name": "Be fit"}


def reorder_aspirations(given: Given) -> Request:
    first, second = aspiration(given.client, "First"), aspiration(given.client, "Second")
    return "POST", "/api/aspirations/reorder", {"ids": [second, first]}


def retire_aspiration(given: Given) -> Request:
    return "POST", f"/api/aspirations/{aspiration(given.client)}/retire", {"itsWork": "pause"}


def bring_back_aspiration(given: Given) -> Request:
    aspiration_id = aspiration(given.client)
    ok(given.client.post(f"/api/aspirations/{aspiration_id}/retire", json={"itsWork": "keep"}))
    return "POST", f"/api/aspirations/{aspiration_id}/bring-back", None


def delete_aspiration(given: Given) -> Request:
    aspiration(given.client, "Stays")
    return "DELETE", f"/api/aspirations/{aspiration(given.client)}", None


# Goals


def create_goal_request(given: Given) -> Request:
    return "PUT", f"/api/goals/{uuid4()}", lifting()


def update_goal(given: Given) -> Request:
    return "PATCH", f"/api/goals/{goal(given.client)}", edit()


def set_weekly_target(given: Given) -> Request:
    return "PUT", f"/api/goals/{goal(given.client)}/weekly-target", FOUR_RUNS


def pause_goal(given: Given) -> Request:
    return "POST", f"/api/goals/{goal(given.client)}/pause", None


def resume_goal(given: Given) -> Request:
    return "POST", f"/api/goals/{goal_after(given.client, 'pause')}/resume", None


def end_goal(given: Given) -> Request:
    return "POST", f"/api/goals/{goal(given.client)}/end", None


def mark_goal_reached(given: Given) -> Request:
    return "POST", f"/api/goals/{goal(given.client)}/mark-reached", None


def reopen_goal(given: Given) -> Request:
    return "POST", f"/api/goals/{goal_after(given.client, 'mark-reached')}/reopen", None


def go_again(given: Given) -> Request:
    return "POST", f"/api/goals/{goal_after(given.client, 'end')}/go-again", None


def delete_goal(given: Given) -> Request:
    goal_id = goal(given.client)
    milestone(given.client, goal_id)
    return "DELETE", f"/api/goals/{goal_id}", None


# Milestones and check-ins


def add_milestone_request(given: Given) -> Request:
    body = {"goalId": goal(given.client), "measurableLine": "Bench 155", "targetDate": None}
    return "PUT", f"/api/milestones/{uuid4()}", body


def update_milestone(given: Given) -> Request:
    milestone_id = milestone(given.client, goal(given.client))
    body = {"measurableLine": "Bench 165", "targetDate": None}
    return "PATCH", f"/api/milestones/{milestone_id}", body


def reorder_milestones(given: Given) -> Request:
    goal_id = goal(given.client)
    first, second = milestone(given.client, goal_id, "M1"), milestone(given.client, goal_id, "M2")
    return "POST", f"/api/goals/{goal_id}/milestones/reorder", {"ids": [second, first]}


def keep_milestone(given: Given) -> Request:
    goal_id = goal(given.client)
    milestone_id = milestone(given.client, goal_id)
    ok(check_in(given.client, goal_id, milestone_id, "notYet", "140"))
    return "POST", f"/api/milestones/{milestone_id}/keep", None


def delete_milestone(given: Given) -> Request:
    goal_id = goal(given.client)
    milestone(given.client, goal_id, "M1")
    second = milestone(given.client, goal_id, "M2")
    milestone(given.client, goal_id, "M3")
    return "DELETE", f"/api/milestones/{second}", None


def check_in_request(given: Given) -> Request:
    goal_id = goal(given.client)
    body = {
        "goalId": goal_id,
        "milestoneId": milestone(given.client, goal_id),
        "outcome": "hit",
        "result": "155",
    }
    return "PUT", f"/api/check-ins/{uuid4()}", body


# Quitting goals


def quitting_day(client: TestClient) -> str:
    goal_id = create_goal(client, no_sugar(startDate="2026-11-01"))["id"]
    return f"/api/goals/{goal_id}/quit-days/{today().isoformat()}"


def urge_day(client: TestClient) -> str:
    goal_id = create_goal(client, no_sugar(startDate="2026-11-01"))["id"]
    return f"/api/goals/{goal_id}/urges/{today().isoformat()}"


def answer_quit_day(given: Given) -> Request:
    return "PUT", quitting_day(given.client), {"held": True}


def clear_quit_day(given: Given) -> Request:
    path = quitting_day(given.client)
    ok(given.client.put(path, json={"held": False}))
    return "POST", f"{path}/clear", None


def rate_urge(given: Given) -> Request:
    return "PUT", urge_day(given.client), {"level": "strong"}


def clear_urge_rating(given: Given) -> Request:
    path = urge_day(given.client)
    ok(given.client.put(path, json={"level": "some"}))
    return "POST", f"{path}/clear", None


# Recurring items


def recurring_item(client: TestClient) -> str:
    return str(ok(client.put(f"/api/recurring-items/{uuid4()}", json=item()))["id"])


def create_recurring_item(given: Given) -> Request:
    return "PUT", f"/api/recurring-items/{uuid4()}", item()


def update_recurring_item(given: Given) -> Request:
    # A new schedule too, so the week's tasks are reworked: sent again, nothing more changes.
    body = item(name="Recycling", schedule={"kind": "flexible", "times": 3, "period": "week"})
    return "PATCH", f"/api/recurring-items/{recurring_item(given.client)}", body


def turn_off_recurring_item(given: Given) -> Request:
    return "POST", f"/api/recurring-items/{recurring_item(given.client)}/turn-off", None


def turn_on_recurring_item(given: Given) -> Request:
    item_id = recurring_item(given.client)
    ok(given.client.post(f"/api/recurring-items/{item_id}/turn-off"))
    return "POST", f"/api/recurring-items/{item_id}/turn-on", None


def delete_recurring_item(given: Given) -> Request:
    return "DELETE", f"/api/recurring-items/{recurring_item(given.client)}", None


# Tasks and weeks


def task(client: TestClient, **body: Any) -> str:
    return str(
        ok(client.put(f"/api/tasks/{uuid4()}", json={"title": "Call the dentist"} | body))["id"]
    )


def on_today(client: TestClient) -> str:
    return task(client, day=today().isoformat())


def add_task(given: Given) -> Request:
    # A day in a week that hasn't opened, the widest case (spec `on-a-day`).
    day = (today() + timedelta(weeks=3)).isoformat()
    return "PUT", f"/api/tasks/{uuid4()}", {"title": "Call the dentist", "day": day}


def update_task(given: Given) -> Request:
    return (
        "PATCH",
        f"/api/tasks/{task(given.client)}",
        {"title": "Call the vet", "timeOfDay": {"kind": "by", "time": "09:30"}},
    )


def check_off_task(given: Given) -> Request:
    body = done_on(today().isoformat(), valueLogged=3.5)
    return "POST", f"/api/tasks/{on_today(given.client)}/check-off", body


def uncheck_task(given: Given) -> Request:
    task_id = on_today(given.client)
    ok(given.client.post(f"/api/tasks/{task_id}/check-off", json=done_on(today().isoformat())))
    return "POST", f"/api/tasks/{task_id}/uncheck", None


def place_task(given: Given) -> Request:
    body = {"week": this_week().isoformat(), "day": today().isoformat()}
    return "POST", f"/api/tasks/{task(given.client)}/place", body


def move_task_to_bank(given: Given) -> Request:
    return "POST", f"/api/tasks/{on_today(given.client)}/bank", {"week": this_week().isoformat()}


def swap_tasks(given: Given) -> Request:
    body = {
        "week": this_week().isoformat(),
        "bankTaskId": task(given.client),
        "day": today().isoformat(),
    }
    return "POST", f"/api/tasks/{on_today(given.client)}/swap", body


def drop_task(given: Given) -> Request:
    return "POST", f"/api/tasks/{task(given.client)}/drop", None


def answer_still_matters(given: Given) -> Request:
    task_id = new_task(given.connection, W3)
    add_rolled_rows(given.connection, task_id, [W1, W2])
    return "POST", f"/api/tasks/{task_id}/still-matters", {"answer": "keep"}


def delete_task(given: Given) -> Request:
    return "DELETE", f"/api/tasks/{on_today(given.client)}", None


def wrap_up_week(given: Given) -> Request:
    given.clock.instant = SUNDAY_EVENING
    task(given.client, day="2026-11-22")
    return "POST", f"/api/weeks/{this_week().isoformat()}/wrap-up", None


# Settings


def set_intensity(given: Given) -> Request:
    return "PUT", "/api/settings/intensity", {"intensity": "goingHard"}


# Sign-in


def sign_out(given: Given) -> Request:
    return "POST", "/api/sign-in/sign-out", None


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
    "answerQuitDay": answer_quit_day,
    "clearQuitDay": clear_quit_day,
    "rateUrge": rate_urge,
    "clearUrgeRating": clear_urge_rating,
    "createRecurringItem": create_recurring_item,
    "updateRecurringItem": update_recurring_item,
    "turnOffRecurringItem": turn_off_recurring_item,
    "turnOnRecurringItem": turn_on_recurring_item,
    "deleteRecurringItem": delete_recurring_item,
    "addTask": add_task,
    "updateTask": update_task,
    "checkOffTask": check_off_task,
    "uncheckTask": uncheck_task,
    "placeTask": place_task,
    "moveTaskToBank": move_task_to_bank,
    "swapTasks": swap_tasks,
    "dropTask": drop_task,
    "answerStillMatters": answer_still_matters,
    "deleteTask": delete_task,
    "wrapUpWeek": wrap_up_week,
    "setIntensity": set_intensity,
    "signOut": sign_out,
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
    operation: str, client: TestClient, connection: Connection, fixed_clock: FixedClock
) -> None:
    client.headers["X-Time-Zone"] = ZONE
    method, path, body = CASES[operation](Given(client, connection, fixed_clock))

    before = snapshot(connection)
    first = client.request(method, path, json=body)
    assert first.status_code < 300, first.text
    after_first = snapshot(connection)
    assert after_first != before, "the first send should change something"
    second = client.request(method, path, json=body)

    assert second.status_code == first.status_code, second.text
    assert second.content == first.content
    assert snapshot(connection) == after_first


# A code and a challenge work once, on purpose (spec `sign-in`).
ONE_SHOT = {"redeemCode", "addPasskey", "startSignIn", "finishSignIn"}


def test_every_write_in_the_api_has_a_case(client: TestClient) -> None:
    schema = client.get("/api/openapi.json").json()
    writes = {
        operation["operationId"]
        for methods in schema["paths"].values()
        for method, operation in methods.items()
        if method in {"put", "post", "patch", "delete"}
    }

    assert writes - CASES.keys() - ONE_SHOT == set()
    assert CASES.keys() - writes == set()
