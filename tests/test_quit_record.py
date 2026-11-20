"""A quitting goal's record on its page: recent days, the run of held days, and the unknown
days inside it (spec `quitting-goals`). Worked out on every read."""

from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.quitting.record import Run, run_of
from tests.test_goals import ZONE, create_goal, lifting, no_sugar
from tests.test_quit_days import answer, ok
from tests.test_urges import rate


def nov(day: int) -> date:
    return date(2026, 11, day)


TODAY = nov(18)


def test_no_answers_is_no_run_and_every_past_day_unknown() -> None:
    assert run_of({}, nov(15), TODAY) == Run(held=0, unknown=3)


def test_a_gap_neither_ends_nor_adds_to_the_run() -> None:
    assert run_of({nov(15): True, nov(17): True}, nov(15), TODAY) == Run(held=2, unknown=1)


def test_a_no_starts_the_run_again_and_gaps_before_it_dont_count() -> None:
    answers = {nov(11): True, nov(14): False, nov(15): True}
    assert run_of(answers, nov(10), TODAY) == Run(held=1, unknown=2)


def test_today_counts_when_answered_but_is_never_unknown() -> None:
    assert run_of({nov(18): True}, nov(18), TODAY) == Run(held=1, unknown=0)
    assert run_of({}, nov(18), TODAY) == Run(held=0, unknown=0)


def test_a_no_today_leaves_an_empty_run() -> None:
    assert run_of({nov(17): True, nov(18): False}, nov(15), TODAY) == Run(held=0, unknown=0)


def test_a_goal_that_has_not_started_has_no_run() -> None:
    assert run_of({}, nov(20), TODAY) == Run(held=0, unknown=0)


@pytest.fixture
def quit_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


def record(client: TestClient, goal_id: str) -> Any:
    return ok(client.get(f"/api/goals/{goal_id}"))["quitRecord"]


def test_the_goals_page_shows_its_days_newest_first(quit_client: TestClient) -> None:
    goal_id = str(create_goal(quit_client, no_sugar(startDate="2026-11-15"))["id"])
    ok(answer(quit_client, goal_id, "2026-11-15", True))
    ok(rate(quit_client, goal_id, "2026-11-17", "strong"))

    found = record(quit_client, goal_id)

    assert [(d["day"], d["held"], d["urge"]) for d in found["days"]] == [
        ("2026-11-18", None, None),
        ("2026-11-17", None, "strong"),
        ("2026-11-16", None, None),
        ("2026-11-15", True, None),
    ]
    assert (found["heldRun"], found["unknownInRun"]) == (1, 2)


def test_filling_in_an_unknown_day_lowers_the_count(quit_client: TestClient) -> None:
    goal_id = str(create_goal(quit_client, no_sugar(startDate="2026-11-15"))["id"])

    ok(answer(quit_client, goal_id, "2026-11-16", True))

    assert (
        record(quit_client, goal_id)["heldRun"],
        record(quit_client, goal_id)["unknownInRun"],
    ) == (1, 2)


def test_the_page_shows_the_last_28_days_and_the_run_reads_further(
    quit_client: TestClient,
) -> None:
    goal_id = str(create_goal(quit_client, no_sugar(startDate="2026-10-01"))["id"])
    ok(answer(quit_client, goal_id, "2026-10-01", True))

    found = record(quit_client, goal_id)

    assert len(found["days"]) == 28
    assert found["days"][-1]["day"] == "2026-10-22"
    assert found["heldRun"] == 1
    assert found["unknownInRun"] == 47  # 2 Oct to 17 Nov


def test_other_goals_have_no_record(quit_client: TestClient) -> None:
    goal_id = str(create_goal(quit_client, lifting())["id"])

    assert record(quit_client, goal_id) is None
