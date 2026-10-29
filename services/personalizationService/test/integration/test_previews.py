"""Verify preview publication and fencing in real PostgreSQL."""

import os
from collections.abc import Callable, Iterator
from dataclasses import replace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, select, update
from sqlalchemy.orm import Session

import personalization.infrastructure.database.preview_repository as adapter
from personalization.application.designs.analysis_record import ResolvedSource
from personalization.application.designs.draft_record import DraftRecord
from personalization.application.errors.file_error import FileError
from personalization.application.files.file_record import FileRecord
from personalization.application.previews.preview import (
    RenderedPreview,
    preview_id,
)
from personalization.application.previews.preview_worker import PreviewWorker
from personalization.application.templates.template_record import (
    Side,
    TemplateRecord,
)
from personalization.bootstrap import create_app
from personalization.infrastructure.config.settings import Settings
from personalization.infrastructure.database.analysis_repository import (
    SqlAlchemyAnalysisSourceRepository,
)
from personalization.infrastructure.database.design_repository import (
    SqlAlchemyDesignRepository,
)
from personalization.infrastructure.database.models.audit_entry import (
    AuditEntryModel,
)
from personalization.infrastructure.database.models.design import DesignModel
from personalization.infrastructure.database.models.image_file import FileModel
from personalization.infrastructure.database.preview_repository import (
    SqlAlchemyPreviewRepository,
)
from personalization.infrastructure.database.template_repository import (
    SqlAlchemyTemplateRepository,
)
from test.files.fakes import BUCKET, StorageServer
from test.image_samples import make_image
from test.integration.test_design_drafts import DraftSeed, condition
from test.integration.test_design_drafts import draft_seed as draft_seed
from test.integration.test_print_versioning import Seed
from test.integration.test_print_versioning import seed as seed
from test.integration.test_templates import series as series
from test.previews.fakes import renderer
from test.security.conftest import claims as claims
from test.security.conftest import jwks_transport as jwks_transport
from test.security.conftest import sign_token as sign_token
from test.security.conftest import signing_keys as signing_keys
from test.security.test_print_http import Ready

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("PERSONALIZATION_DATABASE_INTEGRATION") != "1",
        reason="Requires the disposable PostgreSQL integration database",
    ),
]


@pytest.fixture
def preview_draft(
    engine: Engine, draft_seed: DraftSeed
) -> Iterator[DraftRecord]:
    draft = SqlAlchemyDesignRepository(engine, BUCKET).create(
        draft_seed.owner_id, draft_seed.content
    )
    try:
        yield draft
    finally:
        with Session(engine) as session, session.begin():
            session.execute(
                update(DesignModel)
                .where(DesignModel.user_id == draft.owner_id)
                .values(front_preview_id=None, back_preview_id=None)
            )
            session.execute(
                delete(FileModel).where(
                    FileModel.owner_id == draft.owner_id,
                    FileModel.usage.startswith("PREVIA_V1:"),
                )
            )


def server_for(seed: Seed) -> StorageServer:
    server = StorageServer()
    server.objects[f"{BUCKET}/{seed.file_id}.png"] = make_image()
    return server


@pytest.mark.parametrize(
    "failure", [None, "before-write", "after-write", "publish", "audit"]
)
def test_recovery_publishes_one_pair_atomically_and_preserves_draft(
    engine: Engine,
    preview_draft: DraftRecord,
    seed: Seed,
    monkeypatch: pytest.MonkeyPatch,
    failure: str | None,
) -> None:
    data = preview_draft
    repository = SqlAlchemyPreviewRepository(engine, BUCKET)
    server = server_for(seed)
    storage = server.adapter()
    worker = PreviewWorker(
        repository,
        SqlAlchemyTemplateRepository(engine),
        SqlAlchemyAnalysisSourceRepository(engine, BUCKET),
        storage,
        renderer(),
        BUCKET,
    )
    server.upload_failure = (
        failure if failure in ("before-write", "after-write") else None
    )
    original_publish = repository.publish
    audit_factory = AuditEntryModel

    # Use the same sanitized database failure as an unavailable commit.
    from personalization.application.errors.file_error import FileFailure

    def failed_commit(record: FileRecord) -> FileRecord:
        raise FileError(FileFailure.FILE_DATABASE_UNAVAILABLE)

    with Session(engine) as session:
        collision = session.scalar(
            select(AuditEntryModel.id).where(
                AuditEntryModel.resource_id == data.id
            )
        )

    def failed_audit(**values: object) -> AuditEntryModel:
        values["id"] = collision
        return audit_factory(**values)

    if failure == "publish":
        monkeypatch.setattr(repository, "publish", failed_commit)
    if failure == "audit":
        monkeypatch.setattr(adapter, "AuditEntryModel", failed_audit)
    try:
        assert data.id in repository.candidates(None, 100)
        if failure:
            with pytest.raises(FileError):
                worker.process(data.id)
            assert repository.get_draft(data.id) == data
        server.upload_failure = None
        monkeypatch.setattr(repository, "publish", original_publish)
        monkeypatch.setattr(adapter, "AuditEntryModel", audit_factory)
        assert worker.process(data.id)
        saved = repository.get_draft(data.id)
        assert saved is not None and saved.version == data.version
        assert saved.applications == data.applications
        assert saved.front_preview_id == preview_id(data, Side.FRONT)
        assert saved.back_preview_id == preview_id(data, Side.BACK)
        assert data.id not in repository.candidates(None, 100)
        posts = sum(request.method == "POST" for request in server.requests)
        assert worker.process(data.id)
        assert (
            sum(request.method == "POST" for request in server.requests)
            == posts
        )
        with Session(engine) as session:
            entries = session.scalars(
                select(AuditEntryModel).where(
                    AuditEntryModel.resource_id == data.id,
                    AuditEntryModel.action == "DESIGN_PREVIEWS_GENERATED",
                )
            ).all()
            assert len(entries) == 1 and entries[0].actor_id == data.owner_id
        assert server.objects[f"{BUCKET}/{seed.file_id}.png"] == make_image()
    finally:
        storage.close()


def test_edit_during_render_is_not_overwritten_by_stale_images(
    engine: Engine,
    preview_draft: DraftRecord,
    seed: Seed,
) -> None:
    data = preview_draft
    designs = SqlAlchemyDesignRepository(engine, BUCKET)
    repository = SqlAlchemyPreviewRepository(engine, BUCKET)
    server = server_for(seed)
    storage = server.adapter()
    real_renderer = renderer()

    class RacingRenderer:
        def render(
            self,
            draft: DraftRecord,
            template: TemplateRecord,
            sources: tuple[ResolvedSource, ...],
            read: Callable[[FileRecord], bytes | None],
        ) -> tuple[RenderedPreview, RenderedPreview]:
            result = real_renderer.render(draft, template, sources, read)
            designs.update(
                data.owner_id,
                data.id,
                replace(data.content, applications=()),
                condition(data),
            )
            return result

    try:
        worker = PreviewWorker(
            repository,
            SqlAlchemyTemplateRepository(engine),
            SqlAlchemyAnalysisSourceRepository(engine, BUCKET),
            storage,
            RacingRenderer(),
            BUCKET,
        )
        assert worker.process(data.id) is False
        current = designs.get(data.owner_id, data.id)
        assert current.version == 2 and current.front_preview_id is None
        assert current.back_preview_id is None and current.applications == ()
        worker = PreviewWorker(
            repository,
            SqlAlchemyTemplateRepository(engine),
            SqlAlchemyAnalysisSourceRepository(engine, BUCKET),
            storage,
            real_renderer,
            BUCKET,
        )
        assert worker.process(data.id)
        assert designs.get(
            data.owner_id, data.id
        ).front_preview_id != preview_id(data, Side.FRONT)
    finally:
        storage.close()


def test_advisory_claim_release_and_frozen_attachment_rejection(
    engine: Engine,
    preview_draft: DraftRecord,
) -> None:
    first = SqlAlchemyPreviewRepository(engine, BUCKET)
    second = SqlAlchemyPreviewRepository(engine, BUCKET)
    with pytest.raises(RuntimeError):
        with first.lock(preview_draft.id) as acquired:
            assert acquired
            with second.lock(preview_draft.id) as competing:
                assert not competing
            raise RuntimeError("simulated crash")
    with second.lock(preview_draft.id) as released:
        assert released
    with Session(engine) as session, session.begin():
        row = session.get(DesignModel, preview_draft.id)
        assert row is not None
        row.state = "CONGELADO"
    assert first.attach(preview_draft) is False
    assert preview_draft.id not in first.candidates(None, 100)
    assert first.attach(replace(preview_draft, id=uuid4())) is False


def test_missing_or_corrupt_pair_is_never_attached(
    engine: Engine,
    preview_draft: DraftRecord,
) -> None:
    repository = SqlAlchemyPreviewRepository(engine, BUCKET)
    with pytest.raises(FileError):
        repository.attach(preview_draft)
    assert repository.get_draft(preview_draft.id) == preview_draft


def test_http_ready_and_owned_download_with_signed_jwt(
    engine: Engine,
    preview_draft: DraftRecord,
    seed: Seed,
    settings: Settings,
    sign_token: Callable[..., str],
    claims: dict[str, object],
    jwks_transport: object,
) -> None:
    data = preview_draft
    server = server_for(seed)
    storage = server.adapter()
    repository = SqlAlchemyPreviewRepository(engine, BUCKET)
    app = create_app(
        settings,
        Ready(),
        storage=storage,
        template_repository=SqlAlchemyTemplateRepository(engine),
        design_repository=SqlAlchemyDesignRepository(engine, BUCKET),
        preview_repository=repository,
    )
    headers = {
        "Authorization": "Bearer "
        + sign_token(
            {
                **claims,
                "sub": str(data.owner_id),
                "app_metadata": {"app_role": "administrador"},
            }
        )
    }
    try:
        with TestClient(app) as client:
            path = f"/api/v1/admin/design-drafts/{data.id}/previews"
            assert (
                client.get(path, headers=headers).json()["status"] == "PENDING"
            )
            worker = PreviewWorker(
                repository,
                SqlAlchemyTemplateRepository(engine),
                SqlAlchemyAnalysisSourceRepository(engine, BUCKET),
                storage,
                renderer(),
                BUCKET,
            )
            assert worker.process(data.id)
            read = client.get(path, headers=headers)
            assert read.status_code == 200 and read.json()["status"] == "READY"
            for side in Side:
                signed = client.post(
                    path + f"/{side.value}/download-urls", headers=headers
                )
                assert signed.status_code == 201
                assert signed.headers["Cache-Control"] == "no-store"
            assert (
                client.get(
                    path, headers={"Authorization": "Bearer " + sign_token()}
                ).status_code
                == 403
            )
    finally:
        storage.close()
