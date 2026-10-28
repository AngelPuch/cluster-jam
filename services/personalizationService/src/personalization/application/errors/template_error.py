"""Describe template failures without SQL or external references."""

from enum import StrEnum


class TemplateFailure(StrEnum):
    TEMPLATE_NOT_FOUND = "TEMPLATE_NOT_FOUND"
    TEMPLATE_VERSION_CONFLICT = "TEMPLATE_VERSION_CONFLICT"
    TEMPLATE_VERSION_LIMIT = "TEMPLATE_VERSION_LIMIT"
    TEMPLATE_DATABASE_UNAVAILABLE = "TEMPLATE_DATABASE_UNAVAILABLE"
    INVALID_TEMPLATE_DATA = "INVALID_TEMPLATE_DATA"
    INVALID_CURSOR = "INVALID_CURSOR"
    DUPLICATE_ZONE = "DUPLICATE_ZONE"
    DUPLICATE_ZONE_SIZE = "DUPLICATE_ZONE_SIZE"
    ZONE_OUTSIDE_TEMPLATE = "ZONE_OUTSIDE_TEMPLATE"
    ZONES_OVERLAP = "ZONES_OVERLAP"
    SIZE_OUTSIDE_ZONE = "SIZE_OUTSIDE_ZONE"


class TemplateError(Exception):
    def __init__(self, failure: TemplateFailure) -> None:
        super().__init__(failure.value)
        self.failure = failure
