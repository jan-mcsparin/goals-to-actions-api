from fastapi.testclient import TestClient

from app.config import APP_NAME
from app.main import app

client = TestClient(app)


def test_health_says_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_schema_is_served() -> None:
    schema = client.get("/openapi.json").json()

    assert schema["info"]["title"] == f"{APP_NAME} API"
    assert "/health" in schema["paths"]
