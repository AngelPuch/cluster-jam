"""Adapt the bounded RFC entity-tag parser to draft error codes."""

from personalization.application.designs.draft_record import (
    DesignCondition,
    DraftRecord,
    draft_revision,
)
from personalization.application.errors.design_error import (
    DesignError,
    DesignFailure,
)
from personalization.application.errors.print_error import (
    PrintError,
    PrintFailure,
)
from personalization.interfaces.http.prints.preconditions import parse_if_match


def draft_etag(record: DraftRecord) -> str:
    return '"' + draft_revision(record) + '"'


def draft_condition(values: list[str] | None) -> DesignCondition:
    try:
        parsed = parse_if_match(values)
        return DesignCondition(parsed.revisions, parsed.any_existing)
    except PrintError as error:
        failure = (
            DesignFailure.DESIGN_PRECONDITION_REQUIRED
            if error.failure is PrintFailure.PRINT_PRECONDITION_REQUIRED
            else DesignFailure.INVALID_DESIGN_PRECONDITION
        )
        raise DesignError(failure) from None
