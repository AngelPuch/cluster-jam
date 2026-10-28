"""Validate changes while preserving explicit null descriptions."""

import json
from dataclasses import dataclass, replace
from hashlib import sha256

from personalization.application.errors.print_error import (
    PrintError,
    PrintFailure,
)
from personalization.application.prints.print_record import (
    MAX_DESCRIPTION_LENGTH,
    PrintRecord,
)

EDITABLE_PRINT_FIELDS = frozenset({"name", "description", "active"})


@dataclass(frozen=True)
class PrintChanges:
    fields: frozenset[str]
    name: str | None = None
    description: str | None = None
    active: bool | None = None


@dataclass(frozen=True)
class PrintCondition:
    revisions: frozenset[str] = frozenset()
    any_existing: bool = False

    def matches(self, revision: str) -> bool:
        return self.any_existing or revision in self.revisions


def validate_changes(changes: PrintChanges) -> PrintChanges:
    if not changes.fields or not changes.fields <= EDITABLE_PRINT_FIELDS:
        raise PrintError(PrintFailure.INVALID_PRINT_DATA)
    if "name" in changes.fields:
        if not isinstance(changes.name, str):
            raise PrintError(PrintFailure.INVALID_PRINT_DATA)
        name = changes.name.strip()
        if not 1 <= len(name) <= 120:
            raise PrintError(PrintFailure.INVALID_PRINT_DATA)
        changes = replace(changes, name=name)
    if "description" in changes.fields and changes.description is not None:
        if not isinstance(changes.description, str) or (
            len(changes.description) > MAX_DESCRIPTION_LENGTH
        ):
            raise PrintError(PrintFailure.INVALID_PRINT_DATA)
    if "active" in changes.fields and type(changes.active) is not bool:
        raise PrintError(PrintFailure.INVALID_PRINT_DATA)
    return changes


def print_revision(record: PrintRecord) -> str:
    """Derive a token from every value in the mutable representation."""
    version = record.latest_version
    content = {
        "id": str(record.id),
        "name": record.name,
        "description": record.description,
        "active": record.active,
        "latestVersion": {
            "id": str(version.id),
            "printId": str(version.print_id),
            "number": version.number,
            "fileId": str(version.file_id),
            "surchargeCents": version.surcharge_cents,
            "currency": "MXN",
        },
    }
    encoded = json.dumps(
        content, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return sha256(encoded).hexdigest()
