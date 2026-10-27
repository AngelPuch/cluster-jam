"""Fail closed until real server credentials are configured."""

from personalization.application.errors.file_error import (
    FileError,
    FileFailure,
)
from personalization.application.files.file_record import FileRecord


class UnavailableStorage:
    """Never substitute local files for the required cloud storage."""

    def ensure_private(self) -> None:
        raise FileError(FileFailure.STORAGE_NOT_CONFIGURED)

    def upload(self, record: FileRecord, content: bytes) -> None:
        self.ensure_private()

    def sign_download(self, record: FileRecord, expires_in: int) -> str:
        self.ensure_private()
        raise FileError(FileFailure.STORAGE_NOT_CONFIGURED)

    def verify_original(self, record: FileRecord) -> None:
        self.ensure_private()
