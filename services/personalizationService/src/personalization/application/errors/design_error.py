"""Describe draft persistence errors independently of transports."""

from enum import StrEnum


class DesignFailure(StrEnum):
    DESIGN_NOT_FOUND = "DESIGN_NOT_FOUND"
    DESIGN_NOT_EDITABLE = "DESIGN_NOT_EDITABLE"
    DESIGN_VERSION_LIMIT = "DESIGN_VERSION_LIMIT"
    INVALID_DESIGN_DATA = "INVALID_DESIGN_DATA"
    DESIGN_DATABASE_UNAVAILABLE = "DESIGN_DATABASE_UNAVAILABLE"
    DESIGN_PRECONDITION_REQUIRED = "DESIGN_PRECONDITION_REQUIRED"
    INVALID_DESIGN_PRECONDITION = "INVALID_DESIGN_PRECONDITION"
    DESIGN_PRECONDITION_FAILED = "DESIGN_PRECONDITION_FAILED"
    INVALID_CURSOR = "INVALID_CURSOR"


class DesignError(Exception):
    def __init__(self, failure: DesignFailure) -> None:
        super().__init__(failure.value)
        self.failure = failure
