from typing import Literal

from fastapi import FastAPI

from app.config import APP_NAME
from app.schemas import ApiModel

app = FastAPI(title=f"{APP_NAME} API")


class Health(ApiModel):
    status: Literal["ok"]


@app.get("/health")
def health() -> Health:
    return Health(status="ok")
