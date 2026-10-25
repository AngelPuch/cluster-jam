"""Keep Python identifiers separate from JSON property conventions."""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class RestModel(BaseModel):
    """Use camelCase on the wire and reject unknown input properties."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        extra="forbid",
    )
