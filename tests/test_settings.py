from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.config import FIXED_USER_ID
from tests.test_aspirations import audit_rows
from tests.test_goals import ZONE, today
from tests.test_tasks import add_task
from tests.test_week_read import get_week, this_week


def set_intensity(client: TestClient, intensity: str) -> Any:
    response = client.put("/api/settings/intensity", json={"intensity": intensity})
    assert response.status_code == 200, response.text
    return response.json()


def test_a_new_user_reads_normal(client: TestClient) -> None:
    response = client.get("/api/settings")

    assert response.status_code == 200, response.text
    assert response.json() == {"intensity": "normal"}


def test_a_set_intensity_is_read_back(client: TestClient) -> None:
    assert set_intensity(client, "goingHard") == {"intensity": "goingHard"}

    assert client.get("/api/settings").json() == {"intensity": "goingHard"}


def test_two_word_intensities_are_stored_in_snake_case(
    client: TestClient, connection: Connection
) -> None:
    set_intensity(client, "easingOff")

    stored = connection.execute(
        text("select intensity from users where id = :id"), {"id": FIXED_USER_ID}
    ).scalar_one()
    assert stored == "easing_off"


def test_an_unknown_intensity_is_refused(client: TestClient) -> None:
    for sent in ["going_hard", "turbo", ""]:
        response = client.put("/api/settings/intensity", json={"intensity": sent})
        assert response.status_code == 422, sent

    assert client.get("/api/settings").json() == {"intensity": "normal"}


def test_the_week_marks_days_against_it_and_nothing_moves(client: TestClient) -> None:
    client.headers["X-Time-Zone"] = ZONE
    for n in range(5):
        add_task(client, title=f"Task {n}", day=today().isoformat())
    before = get_week(client, this_week())

    set_intensity(client, "goingHard")
    after = get_week(client, this_week())

    assert after["tasks"] == before["tasks"]
    assert {mark["cap"] for mark in after["days"]} == {6}
    assert not any(mark["full"] for mark in after["days"])


def test_setting_it_twice_changes_nothing_more(client: TestClient, connection: Connection) -> None:
    first = set_intensity(client, "goingHard")
    second = set_intensity(client, "goingHard")

    assert second == first
    actions = [row.action for row in audit_rows(connection, FIXED_USER_ID)]
    assert actions.count("set intensity") == 1
