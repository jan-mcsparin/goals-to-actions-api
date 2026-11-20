"""The OpenAPI schema is the contract with the front end. These tests guard its shape."""

import re
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from app.main import app, operation_id
from app.openapi import OPENAPI_FILE, schema_text

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


def test_the_aspirations_operations_are_in_the_schema() -> None:
    assert set(operation_ids(app.openapi())) >= {
        "listAspirations",
        "createAspiration",
        "updateAspiration",
        "reorderAspirations",
        "retireAspiration",
        "bringBackAspiration",
    }


def test_the_goals_operations_are_in_the_schema() -> None:
    assert set(operation_ids(app.openapi())) >= {
        "listGoals",
        "getGoal",
        "createGoal",
        "updateGoal",
        "setWeeklyTarget",
        "pauseGoal",
        "resumeGoal",
        "endGoal",
        "markGoalReached",
        "reopenGoal",
        "goAgain",
    }


def test_the_milestones_operations_are_in_the_schema() -> None:
    assert set(operation_ids(app.openapi())) >= {
        "addMilestone",
        "updateMilestone",
        "reorderMilestones",
        "keepMilestone",
        "checkIn",
    }


def test_the_delete_operations_are_in_the_schema() -> None:
    assert set(operation_ids(app.openapi())) >= {
        "deleteTask",
        "deleteMilestone",
        "deleteGoal",
        "deleteAspiration",
        "deleteRecurringItem",
    }


def test_every_route_is_served_under_api() -> None:
    outside = [path for path in app.openapi()["paths"] if not path.startswith("/api/")]

    assert outside == []


def test_the_schema_and_docs_are_served_under_api() -> None:
    assert app.openapi_url == "/api/openapi.json"
    assert app.docs_url == "/api/docs"


def test_the_committed_schema_is_up_to_date() -> None:
    assert OPENAPI_FILE.read_text() == schema_text(), (
        "openapi.json is out of date. Run `uv run python -m app.openapi` and commit the result."
    )


def test_the_schema_says_which_errors_a_route_can_send() -> None:
    paths = app.openapi()["paths"]

    assert "404" in paths["/api/aspirations/{aspiration_id}/retire"]["post"]["responses"]
    assert "409" in paths["/api/aspirations/reorder"]["post"]["responses"]
