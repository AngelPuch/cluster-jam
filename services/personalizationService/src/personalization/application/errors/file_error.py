"""Describe safe file failures without provider diagnostics."""

from enum import StrEnum
from uuid import UUID


class FileFailure(StrEnum):
    """Use stable failure codes across transport adapters."""

    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FILE_NOT_READY = "FILE_NOT_READY"
    FILE_DATABASE_UNAVAILABLE = "FILE_DATABASE_UNAVAILABLE"
    STORAGE_NOT_CONFIGURED = "STORAGE_NOT_CONFIGURED"
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"
    STORAGE_BUCKET_UNSAFE = "STORAGE_BUCKET_UNSAFE"
    FILE_INTEGRITY_MISMATCH = "FILE_INTEGRITY_MISMATCH"
    INVALID_MULTIPART = "INVALID_MULTIPART"
    UPLOAD_BODY_TOO_LARGE = "UPLOAD_BODY_TOO_LARGE"
    UPLOAD_BUSY = "UPLOAD_BUSY"
    UPLOAD_TIMEOUT = "UPLOAD_TIMEOUT"
    IMAGE_READ_FAILED = "IMAGE_READ_FAILED"


class FileError(Exception):
    """Retain only a public code when an operation fails."""

    def __init__(
        self,
        failure: FileFailure,
        *,
        file_id: UUID | None = None,
    ) -> None:
        super().__init__(failure.value)
        self.failure = failure
        self.file_id = file_id
