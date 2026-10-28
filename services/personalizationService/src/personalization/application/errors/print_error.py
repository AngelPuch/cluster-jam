"""Describe print failures independently from HTTP and SQL."""

from enum import StrEnum


class PrintFailure(StrEnum):
    PRINT_NOT_FOUND = "PRINT_NOT_FOUND"
    PRINT_VERSION_NOT_FOUND = "PRINT_VERSION_NOT_FOUND"
    PRINT_FILE_NOT_FOUND = "PRINT_FILE_NOT_FOUND"
    INVALID_PRINT_FILE = "INVALID_PRINT_FILE"
    PRINT_VERSION_CONFLICT = "PRINT_VERSION_CONFLICT"
    PRINT_VERSION_LIMIT = "PRINT_VERSION_LIMIT"
    PRINT_DATABASE_UNAVAILABLE = "PRINT_DATABASE_UNAVAILABLE"
    INVALID_PRINT_DATA = "INVALID_PRINT_DATA"
    INVALID_CURSOR = "INVALID_CURSOR"


class PrintError(Exception):
    def __init__(self, failure: PrintFailure) -> None:
        super().__init__(failure.value)
        self.failure = failure
