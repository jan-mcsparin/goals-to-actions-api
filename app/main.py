from typing import Literal

from fastapi import FastAPI
from fastapi.routing import APIRoute
from pydantic.alias_generators import to_camel

from app.config import APP_NAME
from app.schemas import ApiModel


def operation_id(route: APIRoute) -> str:
    """Name each operation after its route function, so generated clients read `checkOffTask`."""
    return to_camel(route.name)


app = FastAPI(title=f"{APP_NAME} API", generate_unique_id_function=operation_id)


class Health(ApiModel):
    status: Literal["ok"]


@app.get("/health")
def health() -> Health:
    return Health(status="ok")
