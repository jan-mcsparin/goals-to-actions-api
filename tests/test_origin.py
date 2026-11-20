"""A write is refused unless it comes from the app's own origin (ADR-012). The founder's other
projects sit on sibling subdomains, which browsers count as the same site, so `SameSite` alone
doesn't keep them out. Reads aren't checked."""

from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import APP_ORIGIN

SIBLING = "https://another-project.jan-mcsparin.me"


def aspiration_names(client: TestClient) -> list[str]:
    listed = client.get("/api/aspirations").json()["aspirations"]
    return [aspiration["name"] for aspiration in listed]


def test_a_write_from_the_apps_origin_lands(client: TestClient) -> None:
    response = client.put(
        f"/api/aspirations/{uuid4()}", json={"name": "Be fit"}, headers={"Origin": APP_ORIGIN}
    )

    assert response.status_code == 200
    assert aspiration_names(client) == ["Be fit"]


def test_a_write_from_a_sibling_subdomain_is_refused(client: TestClient) -> None:
    response = client.put(
        f"/api/aspirations/{uuid4()}", json={"name": "Be fit"}, headers={"Origin": SIBLING}
    )

    assert response.status_code == 403
    assert aspiration_names(client) == []


def test_a_write_with_no_origin_is_refused(client: TestClient) -> None:
    del client.headers["Origin"]

    response = client.put(f"/api/aspirations/{uuid4()}", json={"name": "Be fit"})

    assert response.status_code == 403
    assert aspiration_names(client) == []


def test_every_kind_of_write_is_checked(client: TestClient) -> None:
    aspiration = f"/api/aspirations/{uuid4()}"
    for method, path in (
        ("POST", f"{aspiration}/retire"),
        ("PUT", aspiration),
        ("PATCH", aspiration),
        ("DELETE", aspiration),
    ):
        response = client.request(method, path, headers={"Origin": SIBLING})
        assert response.status_code == 403, method


def test_a_read_from_another_origin_is_answered(client: TestClient) -> None:
    response = client.get("/api/aspirations", headers={"Origin": SIBLING})

    assert response.status_code == 200
