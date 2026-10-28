"""Encode bounded cursors scoped to each administrative collection."""

import base64
import binascii
from uuid import UUID

from personalization.application.errors.print_error import (
    PrintError,
    PrintFailure,
)
from personalization.application.prints.print_record import MAX_VERSION_NUMBER


def encode_cursor(scope: str, value: UUID | int | str) -> str:
    return (
        base64.urlsafe_b64encode(f"1:{scope}:{value}".encode("ascii"))
        .decode("ascii")
        .rstrip("=")
    )


def decode_cursor(cursor: str | None, scope: str) -> str | None:
    if cursor is None:
        return None
    try:
        if not 1 <= len(cursor) <= 256:
            raise ValueError
        content = base64.b64decode(
            cursor + "=" * (-len(cursor) % 4),
            altchars=b"-_",
            validate=True,
        ).decode("ascii")
        prefix = f"1:{scope}:"
        if not content.startswith(prefix):
            raise ValueError
        value = content[len(prefix) :]
        if not value or encode_cursor(scope, value) != cursor:
            raise ValueError
        return value
    except ValueError, binascii.Error, UnicodeError:
        raise PrintError(PrintFailure.INVALID_CURSOR) from None


def print_cursor(cursor: str | None) -> UUID | None:
    value = decode_cursor(cursor, "prints")
    if value is None:
        return None
    try:
        parsed = UUID(value)
        if str(parsed) != value:
            raise ValueError
        return parsed
    except ValueError:
        raise PrintError(PrintFailure.INVALID_CURSOR) from None


def version_cursor(cursor: str | None, print_id: UUID) -> int | None:
    value = decode_cursor(cursor, f"print-versions/{print_id}")
    if value is None:
        return None
    try:
        number = int(value)
        if str(number) != value or not 1 <= number <= MAX_VERSION_NUMBER:
            raise ValueError
        return number
    except ValueError:
        raise PrintError(PrintFailure.INVALID_CURSOR) from None
