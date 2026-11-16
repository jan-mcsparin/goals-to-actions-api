from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic.alias_generators import to_camel

from app.aspirations.routes import router as aspirations_router
from app.config import APP_NAME
from app.errors import NotAllowed, NotFound
from app.schemas import ApiModel


def operation_id(route: APIRoute) -> str:
    """Name each operation after its route function, so generated clients read `checkOffTask`."""
    return to_camel(route.name)


app = FastAPI(title=f"{APP_NAME} API", generate_unique_id_function=operation_id)
app.include_router(aspirations_router)


@app.exception_handler(NotFound)
def not_found(request: Request, error: NotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": "Not Found"})


@app.exception_handler(NotAllowed)
def not_allowed(request: Request, error: NotAllowed) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(error)})


class Health(ApiModel):
    status: Literal["ok"]


@app.get("/health")
def health() -> Health:
    return Health(status="ok")
