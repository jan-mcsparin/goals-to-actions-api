from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.config import FIXED_USER_ID


def create(client: TestClient, name: str, why: str | None = None) -> dict[str, Any]:
    response = client.put(f"/aspirations/{uuid4()}", json={"name": name, "why": why})
    assert response.status_code == 200, response.text
    aspiration: dict[str, Any] = response.json()
    return aspiration


def listed(client: TestClient) -> list[dict[str, Any]]:
    response = client.get("/aspirations")
    assert response.status_code == 200, response.text
    aspirations: list[dict[str, Any]] = response.json()["aspirations"]
    return aspirations


def names_and_positions(client: TestClient) -> list[tuple[str, int | None]]:
    return [(aspiration["name"], aspiration["position"]) for aspiration in listed(client)]


def audit_rows(connection: Connection, row_id: str | UUID) -> list[Any]:
    return list(
        connection.execute(
            text("select user_id, action from audit_log where row_id = :row_id order by id"),
            {"row_id": row_id},
        )
    )


def add_other_user(connection: Connection) -> UUID:
    other_user = uuid4()
    connection.execute(text("insert into users (id) values (:id)"), {"id": other_user})
    return other_user


def add_aspiration_for(connection: Connection, user_id: UUID, name: str) -> UUID:
    aspiration_id = uuid4()
    connection.execute(
        text(
            "insert into aspirations (id, user_id, name, position) values (:id, :user_id, :name, 1)"
        ),
        {"id": aspiration_id, "user_id": user_id, "name": name},
    )
    return aspiration_id


# createAspiration


def test_create_returns_the_aspiration_first_in_priority(client: TestClient) -> None:
    aspiration_id = str(uuid4())

    response = client.put(
        f"/aspirations/{aspiration_id}", json={"name": "Be fit", "why": "To keep up with the kids"}
    )

    assert response.status_code == 200
    aspiration = response.json()
    assert aspiration.pop("createdAt").endswith("Z")
    assert aspiration == {
        "id": aspiration_id,
        "name": "Be fit",
        "why": "To keep up with the kids",
        "status": "active",
        "position": 1,
        "retiredOn": None,
    }


def test_a_new_aspiration_goes_last(client: TestClient) -> None:
    create(client, "Be fit")
    create(client, "Be a good friend")
    create(client, "Write")

    assert names_and_positions(client) == [("Be fit", 1), ("Be a good friend", 2), ("Write", 3)]


def test_why_is_optional(client: TestClient) -> None:
    response = client.put(f"/aspirations/{uuid4()}", json={"name": "Be fit"})

    assert response.json()["why"] is None


def test_name_and_why_are_trimmed_and_a_blank_why_is_empty(client: TestClient) -> None:
    aspiration = create(client, "  Be fit ", "   ")

    assert aspiration["name"] == "Be fit"
    assert aspiration["why"] is None


def test_a_blank_name_is_refused(client: TestClient) -> None:
    response = client.put(f"/aspirations/{uuid4()}", json={"name": "   "})

    assert response.status_code == 422
    assert listed(client) == []


def test_the_same_create_twice_makes_one_aspiration(
    client: TestClient, connection: Connection
) -> None:
    aspiration_id = uuid4()
    body = {"name": "Be fit", "why": None}

    first = client.put(f"/aspirations/{aspiration_id}", json=body)
    second = client.put(f"/aspirations/{aspiration_id}", json=body)

    assert second.status_code == 200
    assert second.json() == first.json()
    assert len(listed(client)) == 1
    assert len(audit_rows(connection, aspiration_id)) == 1


def test_a_repeated_create_returns_the_row_as_it_is(client: TestClient) -> None:
    aspiration_id = uuid4()
    client.put(f"/aspirations/{aspiration_id}", json={"name": "Be fit"})

    again = client.put(f"/aspirations/{aspiration_id}", json={"name": "Be fitter"})

    assert again.json()["name"] == "Be fit"


def test_create_with_another_users_id_is_refused(
    client: TestClient, connection: Connection
) -> None:
    theirs = add_aspiration_for(connection, add_other_user(connection), "Be kind")

    response = client.put(f"/aspirations/{theirs}", json={"name": "Be fit"})

    assert response.status_code == 409
    assert response.json() == {"detail": "That id is already in use."}
    assert listed(client) == []


def test_create_is_audited_with_the_user_and_action(
    client: TestClient, connection: Connection
) -> None:
    aspiration = create(client, "Be fit")

    [row] = audit_rows(connection, aspiration["id"])
    assert row.user_id == FIXED_USER_ID
    assert row.action == "create aspiration"


# listAspirations


def test_list_is_empty_to_begin_with(client: TestClient) -> None:
    assert listed(client) == []


def test_list_gives_active_by_position_then_retired_newest_first(
    client: TestClient, connection: Connection
) -> None:
    create(client, "Be fit")
    create(client, "Write")
    for name, retired_on in [("Learn Welsh", "2026-10-01"), ("Sail", "2026-11-10")]:
        connection.execute(
            text(
                "insert into aspirations (id, user_id, name, status, retired_on) "
                "values (:id, :user_id, :name, 'retired', :retired_on)"
            ),
            {"id": uuid4(), "user_id": FIXED_USER_ID, "name": name, "retired_on": retired_on},
        )

    aspirations = listed(client)

    assert [aspiration["name"] for aspiration in aspirations] == [
        "Be fit",
        "Write",
        "Sail",
        "Learn Welsh",
    ]
    assert aspirations[2]["status"] == "retired"
    assert aspirations[2]["position"] is None
    assert aspirations[2]["retiredOn"] == "2026-11-10"


def test_list_leaves_out_other_users_and_deleted_aspirations(
    client: TestClient, connection: Connection
) -> None:
    add_aspiration_for(connection, add_other_user(connection), "Be kind")
    deleted = create(client, "A mistake")
    connection.execute(
        text("update aspirations set deleted_at = now() where id = :id"), {"id": deleted["id"]}
    )

    assert listed(client) == []
