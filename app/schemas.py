from typing import Any

from pydantic import AfterValidator, BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    """Base for everything the API sends or accepts: snake_case here, camelCase in JSON."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


def refuse_nul(text: str | None) -> str | None:
    if text and "\x00" in text:
        raise ValueError("Text can't contain a NUL character.")
    return text


# For every text field the API accepts: Postgres text can't hold a NUL character.
NoNul = AfterValidator(refuse_nul)


class ErrorMessage(ApiModel):
    """FastAPI's error shape, for the errors the API raises itself."""

    detail: str


# For a route's `responses=`, so the schema says which errors it can send.
NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorMessage, "description": "No such row, or it belongs to someone else."}
}
NOT_ALLOWED: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorMessage, "description": "The rules don't allow this change."}
}
