"""Expose owned preview metadata and short-lived private downloads."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from personalization.application.designs.draft_service import DraftService
from personalization.application.errors.file_error import (
    FileError,
    FileFailure,
)
from personalization.application.files.file_record import (
    FileRecord,
    FileState,
    SignedDownload,
)
from personalization.application.ports.preview_ports import (
    PreviewRepositoryPort,
)
from personalization.application.ports.private_storage_port import (
    PrivateStoragePort,
)
from personalization.application.previews.preview import (
    PreviewStatus,
    check_preview,
)
from personalization.application.security.identity import VerifiedIdentity
from personalization.application.templates.template_record import Side


class PreviewService:
    def __init__(
        self,
        drafts: DraftService,
        repository: PreviewRepositoryPort,
        storage: PrivateStoragePort,
        bucket: str,
        ttl: int,
    ) -> None:
        self._drafts = drafts
        self._repository = repository
        self._storage = storage
        self._bucket = bucket
        self._ttl = ttl

    def get(
        self, identity: VerifiedIdentity, design_id: UUID
    ) -> PreviewStatus:
        draft = self._drafts.get(identity, design_id)
        files: dict[Side, FileRecord | None] = {}
        for side, file_id in (
            (Side.FRONT, draft.front_preview_id),
            (Side.BACK, draft.back_preview_id),
        ):
            record = (
                None if file_id is None else self._repository.get_file(file_id)
            )
            if file_id is not None and (
                record is None
                or record.state is not FileState.AVAILABLE
                or not check_preview(draft, side, record, self._bucket)
            ):
                raise FileError(FileFailure.FILE_INTEGRITY_MISMATCH)
            files[side] = record
        return PreviewStatus(draft, files[Side.FRONT], files[Side.BACK])

    def create_download(
        self, identity: VerifiedIdentity, design_id: UUID, side: Side
    ) -> SignedDownload:
        status = self.get(identity, design_id)
        record = status.front if side is Side.FRONT else status.back
        if record is None:
            raise FileError(FileFailure.FILE_NOT_READY)
        self._storage.ensure_private()
        expires = datetime.now(UTC) + timedelta(seconds=self._ttl)
        return SignedDownload(
            record.id, expires, self._storage.sign_download(record, self._ttl)
        )
