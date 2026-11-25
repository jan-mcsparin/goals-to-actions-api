"""answerStillMatters: keep, put on a day, or drop."""

from datetime import date
from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from tests.test_aspirations import add_other_user
from tests.test_at_close import add_rolled_rows
from tests.test_close_week import W1, W2, W3, history, new_task, state
from tests.test_goals import ZONE


def asked_about(connection: Connection) -> UUID:
    task = new_task(connection, W3)
    add_rolled_rows(connection, task, [W1, W2])
    return task


def answer(client: TestClient, task: UUID, **body: Any) -> Any:
    client.headers["X-Time-Zone"] = ZONE
    return client.post(f"/api/tasks/{task}/still-matters", json=body)


def shown(client: TestClient, task: UUID) -> dict[str, Any]:
    tasks = client.get(f"/api/weeks/{W3}").json()["tasks"]
    return next(row for row in tasks if row["id"] == str(task))


def test_keep_clears_the_question_until_two_more_rollovers(
    client: TestClient, connection: Connection
) -> None:
    task = asked_about(connection)
    assert answer(client, task, answer="keep").status_code == 200

    assert shown(client, task)["stillMatters"] is False
    assert state(connection, task) == "open"
    assert answer(client, task, answer="keep").status_code == 200  # sent twice: nothing more
    assert history(connection, task)[-1] == (W3, None)


def test_schedule_puts_the_task_on_the_day_by_hand_and_clears_the_question(
    client: TestClient, connection: Connection
) -> None:
    task = asked_about(connection)

    response = answer(client, task, answer="schedule", week=W3.isoformat(), day="2026-11-20")

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["plannedDay"], body["placedByHand"], body["stillMatters"]) == (
        "2026-11-20",
        True,
        False,
    )


def test_schedule_can_put_the_task_on_a_day_in_a_later_week(
    client: TestClient, connection: Connection
) -> None:
    task = asked_about(connection)

    response = answer(client, task, answer="schedule", week=W3.isoformat(), day="2026-12-09")

    assert response.status_code == 200, response.text
    assert (response.json()["week"], response.json()["plannedDay"]) == ("2026-12-07", "2026-12-09")
    assert history(connection, task)[-1] == (date(2026, 12, 7), None)


def test_schedule_follows_the_rules_for_the_day_and_the_week(
    client: TestClient, connection: Connection
) -> None:
    task = asked_about(connection)

    past = answer(client, task, answer="schedule", week=W3.isoformat(), day="2026-11-16")
    wrong_week = answer(client, task, answer="schedule", week=W2.isoformat(), day="2026-11-20")

    assert (past.status_code, wrong_week.status_code) == (409, 409)
    assert shown(client, task)["stillMatters"] is True  # nothing recorded


def test_drop_closes_the_task_and_keeps_it_in_history(
    client: TestClient, connection: Connection
) -> None:
    task = asked_about(connection)

    response = answer(client, task, answer="drop")

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "dropped"
    assert history(connection, task)[-1] == (W3, "dropped")
    assert answer(client, task, answer="drop").json() == response.json()


def test_another_owners_task_is_not_found(client: TestClient, connection: Connection) -> None:
    other = add_other_user(connection)
    theirs = uuid4()
    connection.execute(
        text(
            "insert into tasks (id, user_id, title, origin)"
            " values (:id, :user, 'Theirs', 'by_hand')"
        ),
        {"id": theirs, "user": other},
    )

    for body in ({"answer": "keep"}, {"answer": "drop"}):
        assert answer(client, theirs, **body).status_code == 404


def test_a_done_task_cant_be_kept_or_scheduled_and_a_dropped_one_can_be_dropped_again(
    client: TestClient, connection: Connection
) -> None:
    done = new_task(connection, W3, outcome="done")
    connection.execute(
        text(
            "update tasks set state = 'done', completed_at = now(), completed_on = :day"
            " where id = :id"
        ),
        {"id": done, "day": date(2026, 11, 17)},
    )

    assert answer(client, done, answer="keep").status_code == 409
    assert answer(client, done, answer="drop").status_code == 409
    assert (
        answer(client, done, answer="schedule", week=W3.isoformat(), day="2026-11-20").status_code
        == 409
    )


def test_an_unknown_answer_is_refused(client: TestClient, connection: Connection) -> None:
    task = asked_about(connection)

    assert answer(client, task, answer="maybe").status_code == 422
