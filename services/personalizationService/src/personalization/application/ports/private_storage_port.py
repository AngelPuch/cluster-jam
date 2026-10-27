"""Store immutable originals through a private storage adapter."""

from typing import Protocol

from personalization.application.files.file_record import FileRecord


class PrivateStoragePort(Protocol):
    """Never overwrite or publish an original through a public URL."""

    def ensure_private(self) -> None:
        """Require the configured private bucket and its
        upload limits.
        """
        ...

    def upload(self, record: FileRecord, content: bytes) -> None:
        """Create the immutable object without automatic retries."""
        ...

    def sign_download(self, record: FileRecord, expires_in: int) -> str:
        """Return a short-lived URL for an already authorized record."""
        ...

    def verify_original(self, record: FileRecord) -> None:
        """Verify remote bytes against durable metadata for recovery."""
        ...
