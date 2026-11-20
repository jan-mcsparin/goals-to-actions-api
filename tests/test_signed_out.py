"""Every route but `health` and the sign-in routes answers 401 without a session (spec
`sign-in`). The test reads the schema, so a new route is covered the day it's added."""

from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

OPEN_PATHS = {"/api/health"}
OPEN_PREFIX = "/api/sign-in/"


def path_value(parameter: dict[str, Any]) -> str:
    if parameter["schema"].get("format") == "date":
        return "2026-11-18"
    return str(uuid4())


def operations() -> list[tuple[str, str, str]]:
    """(operation id, method, a path with every parameter filled) for each protected route."""
    found = []
    for path, methods in app.openapi()["paths"].items():
        if path in OPEN_PATHS or path.startswith(OPEN_PREFIX):
            continue
        for method, operation in methods.items():
            filled = path
            for parameter in operation.get("parameters", []):
                if parameter["in"] == "path":
                    filled = filled.replace(f"{{{parameter['name']}}}", path_value(parameter))
            found.append((operation["operationId"], method.upper(), filled))
    return found


def test_every_route_but_health_and_sign_in_refuses_a_request_with_no_session(
    client: TestClient,
) -> None:
    client.cookies.clear()

    answers = {
        operation_id: client.request(method, path).status_code
        for operation_id, method, path in operations()
    }

    assert answers and {status for status in answers.values()} == {401}, answers


def test_health_answers_with_no_session(client: TestClient) -> None:
    client.cookies.clear()

    assert client.get("/api/health").status_code == 200
