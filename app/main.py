from typing import Literal

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic.alias_generators import to_camel

from app.aspirations.routes import router as aspirations_router
from app.config import APP_NAME
from app.errors import NotAllowed, NotFound
from app.goals.routes import router as goals_router
from app.milestones.routes import router as milestones_router
from app.quitting.routes import router as quitting_router
from app.recurring_items.routes import router as recurring_items_router
from app.schemas import ApiModel
from app.settings.routes import router as settings_router
from app.tasks.routes import router as tasks_router
from app.turnover.routes import router as turnover_router


def operation_id(route: APIRoute) -> str:
    """Name each operation after its route function, so generated clients read `checkOffTask`."""
    return to_camel(route.name)


class Health(ApiModel):
    status: Literal["ok"]


# Every route sits under /api, locally as well as hosted: CloudFront passes `/api/*` on
# unchanged (ADR-011), so a request looks the same through the dev proxy and in production.
api = APIRouter(prefix="/api")


@api.get("/health")
def health() -> Health:
    return Health(status="ok")


api.include_router(aspirations_router)
api.include_router(goals_router)
api.include_router(milestones_router)
api.include_router(quitting_router)
api.include_router(recurring_items_router)
api.include_router(settings_router)
api.include_router(tasks_router)
api.include_router(turnover_router)

app = FastAPI(
    title=f"{APP_NAME} API",
    generate_unique_id_function=operation_id,
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url=None,
)
app.include_router(api)


@app.exception_handler(NotFound)
def not_found(request: Request, error: NotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": "Not Found"})


@app.exception_handler(NotAllowed)
def not_allowed(request: Request, error: NotAllowed) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(error)})
