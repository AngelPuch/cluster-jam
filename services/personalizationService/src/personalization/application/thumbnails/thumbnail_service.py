"""Authorize administrative inspection of worker results."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from personalization.application.errors.file_error import (
    FileError,
    FileFailure,
)
from personalization.application.files.file_record import (
    FileRecord,
    FileState,
    SignedDownload,
)
from personalization.application.ports.print_repository_port import (
    PrintRepositoryPort,
)
from personalization.application.ports.private_storage_port import (
    PrivateStoragePort,
)
from personalization.application.ports.thumbnail_ports import (
    ThumbnailRepositoryPort,
)
from personalization.application.prints.print_service import (
    require_administrator,
)
from personalization.application.security.identity import VerifiedIdentity
from personalization.application.thumbnails.thumbnail import (
    THUMBNAIL_SIDE_PX,
    THUMBNAIL_USAGE_PREFIX,
    thumbnail_id,
)


class ThumbnailService:
    def __init__(
        self,
        prints: PrintRepositoryPort,
        repository: ThumbnailRepositoryPort,
        storage: PrivateStoragePort,
        bucket: str,
        ttl: int,
    ) -> None:
        self._prints = prints
        self._repository = repository
        self._storage = storage
        self._bucket = bucket
        self._ttl = ttl

    def get(
        self, identity: VerifiedIdentity, print_id: UUID, version_id: UUID
    ) -> FileRecord:
        require_administrator(identity)
        version = self._prints.get_version(print_id, version_id)
        record = self._repository.get(version.file_id)
        if record is None or record.state is not FileState.AVAILABLE:
            raise FileError(FileFailure.FILE_NOT_READY)
        if (
            record.id != thumbnail_id(version.file_id)
            or record.mime_type != "image/png"
            or record.object_key != f"{record.id}.png"
            or not 1 <= record.width_px <= THUMBNAIL_SIDE_PX
            or not 1 <= record.height_px <= THUMBNAIL_SIDE_PX
            or record.bucket != self._bucket
            or record.usage != THUMBNAIL_USAGE_PREFIX + str(version.file_id)
        ):
            raise FileError(FileFailure.FILE_INTEGRITY_MISMATCH)
        return record

    def create_download(
        self, identity: VerifiedIdentity, print_id: UUID, version_id: UUID
    ) -> SignedDownload:
        record = self.get(identity, print_id, version_id)
        self._storage.ensure_private()
        expires = datetime.now(UTC) + timedelta(seconds=self._ttl)
        url = self._storage.sign_download(record, self._ttl)
        return SignedDownload(record.id, expires, url)
