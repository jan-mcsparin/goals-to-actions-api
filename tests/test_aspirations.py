from datetime import datetime
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

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


# reorderAspirations


def reorder(client: TestClient, ids: list[str]) -> Any:
    return client.post("/aspirations/reorder", json={"ids": ids})


def test_reorder_numbers_the_active_aspirations_in_the_order_sent(client: TestClient) -> None:
    fit, friend, write = (create(client, name) for name in ["Be fit", "Be a good friend", "Write"])

    response = reorder(client, [write["id"], fit["id"], friend["id"]])

    assert response.status_code == 200
    assert [(a["name"], a["position"]) for a in response.json()["aspirations"]] == [
        ("Write", 1),
        ("Be fit", 2),
        ("Be a good friend", 3),
    ]
    assert names_and_positions(client) == [("Write", 1), ("Be fit", 2), ("Be a good friend", 3)]


def test_reorder_leaves_retired_aspirations_alone(
    client: TestClient, connection: Connection
) -> None:
    fit, write = create(client, "Be fit"), create(client, "Write")
    connection.execute(
        text(
            "insert into aspirations (id, user_id, name, status, retired_on) "
            "values (:id, :user_id, 'Sail', 'retired', '2026-11-10')"
        ),
        {"id": uuid4(), "user_id": FIXED_USER_ID},
    )

    reorder(client, [write["id"], fit["id"]])

    assert names_and_positions(client) == [("Write", 1), ("Be fit", 2), ("Sail", None)]


def test_reorder_refuses_a_list_that_is_not_exactly_the_active_ones(
    client: TestClient, connection: Connection
) -> None:
    fit, write = create(client, "Be fit"), create(client, "Write")
    theirs = add_aspiration_for(connection, add_other_user(connection), "Be kind")
    wrong_lists = {
        "one left out": [write["id"]],
        "one repeated": [write["id"], write["id"]],
        "one repeated as well": [write["id"], fit["id"], write["id"]],
        "one unknown": [write["id"], fit["id"], str(uuid4())],
        "another user's": [write["id"], fit["id"], str(theirs)],
    }

    for what, ids in wrong_lists.items():
        response = reorder(client, ids)

        assert response.status_code == 409, what
        assert response.json() == {"detail": "The order must list every active aspiration once."}
        assert names_and_positions(client) == [("Be fit", 1), ("Write", 2)], what


def test_reorder_refuses_a_retired_aspiration(client: TestClient, connection: Connection) -> None:
    fit = create(client, "Be fit")
    retired = uuid4()
    connection.execute(
        text(
            "insert into aspirations (id, user_id, name, status, retired_on) "
            "values (:id, :user_id, 'Sail', 'retired', '2026-11-10')"
        ),
        {"id": retired, "user_id": FIXED_USER_ID},
    )

    assert reorder(client, [fit["id"], str(retired)]).status_code == 409


def test_the_same_order_twice_changes_nothing_more(
    client: TestClient, connection: Connection
) -> None:
    fit, write = create(client, "Be fit"), create(client, "Write")

    reorder(client, [write["id"], fit["id"]])
    again = reorder(client, [write["id"], fit["id"]])

    assert again.status_code == 200
    assert names_and_positions(client) == [("Write", 1), ("Be fit", 2)]
    assert [row.action for row in audit_rows(connection, fit["id"])] == [
        "create aspiration",
        "reorder aspirations",
    ]


def test_reorder_with_no_aspirations_is_fine(client: TestClient) -> None:
    response = reorder(client, [])

    assert response.status_code == 200
    assert response.json() == {"aspirations": []}


# updateAspiration


def test_update_changes_name_and_why_and_nothing_else(client: TestClient) -> None:
    create(client, "Be fit")
    write = create(client, "Write", "I have things to say")

    response = client.patch(
        f"/aspirations/{write['id']}", json={"name": " Write daily ", "why": "It clears my head"}
    )

    assert response.status_code == 200
    assert response.json() == write | {"name": "Write daily", "why": "It clears my head"}
    assert names_and_positions(client) == [("Be fit", 1), ("Write daily", 2)]


def test_update_with_no_why_empties_it(client: TestClient) -> None:
    write = create(client, "Write", "I have things to say")

    response = client.patch(f"/aspirations/{write['id']}", json={"name": "Write", "why": None})

    assert response.json()["why"] is None


def test_update_works_on_a_retired_aspiration(client: TestClient, connection: Connection) -> None:
    retired = uuid4()
    connection.execute(
        text(
            "insert into aspirations (id, user_id, name, status, retired_on) "
            "values (:id, :user_id, 'Sail', 'retired', '2026-11-10')"
        ),
        {"id": retired, "user_id": FIXED_USER_ID},
    )

    response = client.patch(f"/aspirations/{retired}", json={"name": "Sail the coast"})

    assert response.status_code == 200
    assert response.json()["name"] == "Sail the coast"
    assert response.json()["retiredOn"] == "2026-11-10"


def test_update_of_an_unknown_or_another_users_aspiration_is_not_found(
    client: TestClient, connection: Connection
) -> None:
    theirs = add_aspiration_for(connection, add_other_user(connection), "Be kind")

    for aspiration_id in [uuid4(), theirs]:
        response = client.patch(f"/aspirations/{aspiration_id}", json={"name": "Mine now"})

        assert response.status_code == 404
        assert response.json() == {"detail": "Not Found"}
    name = connection.execute(
        text("select name from aspirations where id = :id"), {"id": theirs}
    ).scalar_one()
    assert name == "Be kind"


def test_update_refuses_a_blank_name(client: TestClient) -> None:
    write = create(client, "Write")

    response = client.patch(f"/aspirations/{write['id']}", json={"name": ""})

    assert response.status_code == 422
    assert names_and_positions(client) == [("Write", 1)]


def test_update_is_audited(client: TestClient, connection: Connection) -> None:
    write = create(client, "Write")

    client.patch(f"/aspirations/{write['id']}", json={"name": "Write daily"})

    assert audit_rows(connection, write["id"])[-1].action == "update aspiration"


# retireAspiration

FAR_EAST = "Pacific/Kiritimati"


def retire(client: TestClient, aspiration_id: str | UUID, time_zone: str = FAR_EAST) -> Any:
    return client.post(f"/aspirations/{aspiration_id}/retire", headers={"X-Time-Zone": time_zone})


def bring_back(client: TestClient, aspiration_id: str | UUID) -> Any:
    return client.post(f"/aspirations/{aspiration_id}/bring-back")


def test_retire_empties_the_position_and_sets_the_day_in_the_phones_time_zone(
    client: TestClient,
) -> None:
    fit = create(client, "Be fit")

    response = retire(client, fit["id"], FAR_EAST)

    assert response.status_code == 200
    assert response.json() == fit | {
        "status": "retired",
        "position": None,
        "retiredOn": datetime.now(ZoneInfo(FAR_EAST)).date().isoformat(),
    }


def test_the_retired_day_follows_the_time_zone(client: TestClient) -> None:
    east = retire(client, create(client, "Be fit")["id"], "Pacific/Kiritimati").json()
    west = retire(client, create(client, "Write")["id"], "Pacific/Pago_Pago").json()

    assert east["retiredOn"] > west["retiredOn"]


def test_retire_closes_the_gap_it_leaves(client: TestClient) -> None:
    create(client, "Be fit")
    friend = create(client, "Be a good friend")
    create(client, "Write")
    create(client, "Sail")

    retire(client, friend["id"])

    assert names_and_positions(client) == [
        ("Be fit", 1),
        ("Write", 2),
        ("Sail", 3),
        ("Be a good friend", None),
    ]


def test_retiring_twice_changes_nothing(client: TestClient, connection: Connection) -> None:
    fit = create(client, "Be fit")
    create(client, "Write")

    first = retire(client, fit["id"], "Pacific/Pago_Pago")
    second = retire(client, fit["id"], "Pacific/Kiritimati")

    assert second.status_code == 200
    assert second.json() == first.json()
    assert names_and_positions(client) == [("Write", 1), ("Be fit", None)]
    assert [row.action for row in audit_rows(connection, fit["id"])] == [
        "create aspiration",
        "retire aspiration",
    ]


def test_retire_needs_a_time_zone_it_knows(client: TestClient) -> None:
    fit = create(client, "Be fit")

    missing = client.post(f"/aspirations/{fit['id']}/retire")
    unknown = retire(client, fit["id"], "Mars/Olympus_Mons")

    assert missing.status_code == 422
    assert unknown.status_code == 422
    assert names_and_positions(client) == [("Be fit", 1)]


def test_retire_of_an_unknown_or_another_users_aspiration_is_not_found(
    client: TestClient, connection: Connection
) -> None:
    theirs = add_aspiration_for(connection, add_other_user(connection), "Be kind")

    for aspiration_id in [uuid4(), theirs]:
        assert retire(client, aspiration_id).status_code == 404
    status = connection.execute(
        text("select status from aspirations where id = :id"), {"id": theirs}
    ).scalar_one()
    assert status == "active"


# bringBackAspiration


def test_bring_back_makes_it_active_and_last(client: TestClient) -> None:
    fit = create(client, "Be fit")
    create(client, "Write")
    create(client, "Sail")
    retire(client, fit["id"])

    response = bring_back(client, fit["id"])

    assert response.status_code == 200
    assert response.json() == fit | {"position": 3}
    assert names_and_positions(client) == [("Write", 1), ("Sail", 2), ("Be fit", 3)]


def test_bringing_back_the_only_aspiration_makes_it_first(client: TestClient) -> None:
    fit = create(client, "Be fit")
    retire(client, fit["id"])

    assert bring_back(client, fit["id"]).json()["position"] == 1


def test_bringing_back_an_active_aspiration_changes_nothing(
    client: TestClient, connection: Connection
) -> None:
    fit = create(client, "Be fit")
    create(client, "Write")

    response = bring_back(client, fit["id"])

    assert response.status_code == 200
    assert response.json() == fit
    assert names_and_positions(client) == [("Be fit", 1), ("Write", 2)]
    assert len(audit_rows(connection, fit["id"])) == 1


def test_bring_back_of_an_unknown_or_another_users_aspiration_is_not_found(
    client: TestClient, connection: Connection
) -> None:
    theirs = add_aspiration_for(connection, add_other_user(connection), "Be kind")

    for aspiration_id in [uuid4(), theirs]:
        assert bring_back(client, aspiration_id).status_code == 404


def test_retire_and_bring_back_are_audited(client: TestClient, connection: Connection) -> None:
    fit = create(client, "Be fit")
    write = create(client, "Write")

    retire(client, fit["id"])
    bring_back(client, fit["id"])

    assert [row.action for row in audit_rows(connection, fit["id"])] == [
        "create aspiration",
        "retire aspiration",
        "bring back aspiration",
    ]
    # Closing the gap is part of the retire.
    assert audit_rows(connection, write["id"])[-1].action == "retire aspiration"
