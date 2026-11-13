"""The OpenAPI schema is the contract with the front end. These tests guard its shape."""

import re
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from app.main import app, operation_id

CAMEL_CASE = re.compile(r"^[a-z][a-zA-Z0-9]*$")


def property_names_not_in_camel_case(schema: dict[str, Any]) -> list[str]:
    models = schema.get("components", {}).get("schemas", {})
    return [
        f"{model_name}.{property_name}"
        for model_name, model in models.items()
        for property_name in model.get("properties", {})
        if not CAMEL_CASE.match(property_name)
    ]


def operation_ids(schema: dict[str, Any]) -> list[str]:
    return [
        operation["operationId"] for path in schema["paths"].values() for operation in path.values()
    ]


def test_every_property_in_the_schema_is_camel_case() -> None:
    assert property_names_not_in_camel_case(app.openapi()) == []


def test_a_model_that_skips_api_model_is_caught() -> None:
    class PlainModel(BaseModel):
        planned_day: str

    stray = FastAPI()

    @stray.get("/stray")
    def read_stray() -> PlainModel:
        return PlainModel(planned_day="2026-11-17")

    assert property_names_not_in_camel_case(stray.openapi()) == ["PlainModel.planned_day"]


def test_operations_are_named_after_their_route_functions() -> None:
    assert "health" in operation_ids(app.openapi())


def test_operation_names_are_camel_case_and_unique() -> None:
    named = FastAPI(generate_unique_id_function=operation_id)

    @named.post("/tasks/{task_id}/check-off")
    def check_off_task(task_id: str) -> None: ...

    assert operation_ids(named.openapi()) == ["checkOffTask"]

    ids = operation_ids(app.openapi())
    assert len(ids) == len(set(ids))
