"""Coordinate durable uploads and explicit owner/admin access."""

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
from personalization.application.images.validate_image_service import (
    ValidateImageService,
)
from personalization.application.ports.file_repository_port import (
    FileRepositoryPort,
)
from personalization.application.ports.image_source_port import ImageSourcePort
from personalization.application.ports.private_storage_port import (
    PrivateStoragePort,
)
from personalization.application.security.identity import VerifiedIdentity
from personalization.application.security.permissions import (
    require_resource_owner,
)


class FileService:
    """Keep external I/O outside local database transactions."""

    def __init__(
        self,
        validator: ValidateImageService,
        repository: FileRepositoryPort,
        storage: PrivateStoragePort,
        bucket: str,
        download_ttl: int,
    ) -> None:
        self._validator = validator
        self._repository = repository
        self._storage = storage
        self._bucket = bucket
        self._download_ttl = download_ttl

    def upload(
        self,
        identity: VerifiedIdentity,
        source: ImageSourcePort,
        declared_mime: str | None,
    ) -> FileRecord:
        """Retain an intention even when upload or commit is
        ambiguous.
        """
        image = self._validator.execute(source, declared_mime)
        self._storage.ensure_private()
        record = FileRecord(
            id=image.file_id,
            owner_id=identity.user_id,
            bucket=self._bucket,
            object_key=image.object_key,
            mime_type=image.mime_type,
            size_bytes=image.size_bytes,
            width_px=image.width_px,
            height_px=image.height_px,
            sha256=image.sha256,
            state=FileState.PENDING,
        )
        self._repository.create_pending(record)
        try:
            self._storage.upload(record, image.original_bytes)
            return self._repository.make_available(record.id)
        except FileError as error:
            raise FileError(error.failure, file_id=record.id) from None

    def get(self, identity: VerifiedIdentity, file_id: UUID) -> FileRecord:
        """Allow the owner or an explicitly authorized administrator."""
        record = self._get_original(file_id)
        require_resource_owner(
            identity, record.owner_id, allow_administrator=True
        )
        return record

    def create_download(
        self,
        identity: VerifiedIdentity,
        file_id: UUID,
    ) -> SignedDownload:
        """Check ownership and availability before
        contacting Storage.
        """
        record = self.get(identity, file_id)
        if record.state is not FileState.AVAILABLE:
            raise FileError(FileFailure.FILE_NOT_READY)
        self._storage.ensure_private()
        expires_at = datetime.now(UTC) + timedelta(seconds=self._download_ttl)
        url = self._storage.sign_download(record, self._download_ttl)
        return SignedDownload(record.id, expires_at, url)

    def reconcile(self, file_id: UUID) -> FileRecord:
        """Recover only after matching remote bytes; never
        delete data.
        """
        record = self._get_original(file_id)
        if record.state is FileState.AVAILABLE:
            return record
        self._storage.ensure_private()
        self._storage.verify_original(record)
        return self._repository.make_available(record.id)

    def _get_original(self, file_id: UUID) -> FileRecord:
        """Keep preview and other service buckets outside
        this resource.
        """
        record = self._repository.get(file_id)
        if record is None or record.usage != "ORIGINAL":
            raise FileError(FileFailure.FILE_NOT_FOUND)
        return record
