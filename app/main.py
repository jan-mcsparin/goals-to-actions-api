from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, Request
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
from app.sign_in.origin import same_origin
from app.sign_in.routes import router as sign_in_router
from app.sign_in.session import current_user_id
from app.tasks.routes import router as tasks_router
from app.turnover.routes import router as turnover_router


def operation_id(route: APIRoute) -> str:
    """Name each operation after its route function, so generated clients read `checkOffTask`."""
    return to_camel(route.name)


class Health(ApiModel):
    status: Literal["ok"]


# Every route sits under /api, locally as well as hosted: CloudFront passes `/api/*` on
# unchanged (ADR-011), so a request looks the same through the dev proxy and in production.
# A write from anywhere but the app's own origin is a 403, before anything else is checked.
api = APIRouter(prefix="/api", dependencies=[Depends(same_origin)])


@api.get("/health")
def health() -> Health:
    return Health(status="ok")


# Open without a session: they're how one starts.
api.include_router(sign_in_router)


# Every route below answers 401 without a session (ADR-012). Listed here as well as asked for
# by each route, so the 401 comes before any 422 for a missing header or body.
signed_in = APIRouter(dependencies=[Depends(current_user_id)])
signed_in.include_router(aspirations_router)
signed_in.include_router(goals_router)
signed_in.include_router(milestones_router)
signed_in.include_router(quitting_router)
signed_in.include_router(recurring_items_router)
signed_in.include_router(settings_router)
signed_in.include_router(tasks_router)
signed_in.include_router(turnover_router)
api.include_router(signed_in)

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
