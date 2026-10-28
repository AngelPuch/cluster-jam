"""Map HTTP validators onto representation revision conditions."""

import re

from personalization.application.errors.print_error import (
    PrintError,
    PrintFailure,
)
from personalization.application.prints.print_changes import (
    PrintCondition,
    print_revision,
)
from personalization.application.prints.print_record import PrintRecord

MAX_IF_MATCH_LENGTH = 2048
MAX_ENTITY_TAGS = 32
ENTITY_TAG = re.compile(r'(W/)?"([\x21\x23-\x7e\x80-\xff]*)"')
ETAG_RESPONSE: dict[str, object] = {
    "headers": {
        "ETag": {
            "description": "Strong validator to send unchanged in If-Match",
            "schema": {"type": "string"},
        },
    },
}


def print_etag(record: PrintRecord) -> str:
    return '"' + print_revision(record) + '"'


def parse_if_match(values: list[str] | None) -> PrintCondition:
    """Bound the list, preserve opaque commas and ignore weak tags."""
    if values is None:
        raise PrintError(PrintFailure.PRINT_PRECONDITION_REQUIRED)
    if sum(len(value) + 1 for value in values) > MAX_IF_MATCH_LENGTH:
        raise PrintError(PrintFailure.INVALID_PRINT_PRECONDITION)
    value = ",".join(values).strip(" \t")
    if value == "*":
        return PrintCondition(any_existing=True)
    revisions: set[str] = set()
    position = 0
    count = 0
    # Ignore empty list elements within the total-size bound.
    while position < len(value):
        if value[position] in " \t,":
            position += 1
            continue
        match = ENTITY_TAG.match(value, position)
        if match is None:
            raise PrintError(PrintFailure.INVALID_PRINT_PRECONDITION)
        count += 1
        if count > MAX_ENTITY_TAGS:
            raise PrintError(PrintFailure.INVALID_PRINT_PRECONDITION)
        if match.group(1) is None:
            revisions.add(match.group(2))
        position = match.end()
        while position < len(value) and value[position] in " \t":
            position += 1
        if position < len(value) and value[position] != ",":
            raise PrintError(PrintFailure.INVALID_PRINT_PRECONDITION)
    if count == 0:
        raise PrintError(PrintFailure.INVALID_PRINT_PRECONDITION)
    return PrintCondition(frozenset(revisions))
