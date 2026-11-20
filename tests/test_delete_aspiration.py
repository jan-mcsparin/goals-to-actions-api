"""Deleting an aspiration made by mistake (spec `delete`): the ones below it move up, and its
goals and recurring items stay with no aspiration."""

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from tests.test_aspirations import (
    add_aspiration_for,
    add_other_user,
    audit_rows,
    create,
    names_and_positions,
    retire,
)
from tests.test_goals import ZONE, create_goal, lifting
from tests.test_recurring_items import create as create_item
from tests.test_recurring_items import item, listed


@pytest.fixture
def zoned_client(client: TestClient) -> Iterator[TestClient]:
    client.headers["X-Time-Zone"] = ZONE
    yield client


def delete_aspiration(client: TestClient, aspiration_id: str) -> Any:
    return client.delete(f"/api/aspirations/{aspiration_id}")


def test_the_ones_below_move_up_and_a_new_one_goes_last(zoned_client: TestClient) -> None:
    first = create(zoned_client, "Be fit")
    create(zoned_client, "Grow")
    create(zoned_client, "Rest")

    response = delete_aspiration(zoned_client, first["id"])

    assert response.status_code == 204
    assert "content-type" not in response.headers
    create(zoned_client, "Play")
    assert names_and_positions(zoned_client) == [("Grow", 1), ("Rest", 2), ("Play", 3)]


def test_a_retired_one_goes_without_renumbering(zoned_client: TestClient) -> None:
    create(zoned_client, "Be fit")
    retired = create(zoned_client, "Grow")
    create(zoned_client, "Rest")
    retire(zoned_client, retired["id"])

    delete_aspiration(zoned_client, retired["id"])

    assert names_and_positions(zoned_client) == [("Be fit", 1), ("Rest", 2)]


def test_its_goals_and_items_stay_with_no_aspiration(zoned_client: TestClient) -> None:
    aspiration = create(zoned_client, "Be fit")
    goal = create_goal(zoned_client, lifting(aspirationId=aspiration["id"]))
    kept = create_item(zoned_client, item(aspirationId=aspiration["id"]))

    delete_aspiration(zoned_client, aspiration["id"])

    found = zoned_client.get(f"/api/goals/{goal['id']}").json()
    assert found["goal"]["aspirationId"] is None
    assert found["aspiration"] is None
    assert [(i["id"], i["aspirationId"]) for i in listed(zoned_client)] == [(kept["id"], None)]


def test_deleting_twice_changes_nothing_more(
    zoned_client: TestClient, connection: Connection
) -> None:
    aspiration = create(zoned_client, "Be fit")
    delete_aspiration(zoned_client, aspiration["id"])

    assert delete_aspiration(zoned_client, aspiration["id"]).status_code == 204
    assert [row.action for row in audit_rows(connection, aspiration["id"])] == [
        "create aspiration",
        "delete aspiration",
    ]


def test_another_users_aspiration_or_an_unknown_id_is_not_found(
    zoned_client: TestClient, connection: Connection
) -> None:
    theirs = add_aspiration_for(connection, add_other_user(connection), "Theirs")

    assert delete_aspiration(zoned_client, str(theirs)).status_code == 404
    assert delete_aspiration(zoned_client, str(uuid4())).status_code == 404
