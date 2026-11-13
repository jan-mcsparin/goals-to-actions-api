from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    """Base for everything the API sends or accepts: snake_case here, camelCase in JSON."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
