"""Verify recovery, cancellation and revision fencing."""

from collections.abc import Callable
from dataclasses import replace
from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image

from personalization.application.designs.analysis_record import ResolvedSource
from personalization.application.designs.draft_record import (
    DesignCondition,
    DesignState,
    DraftRecord,
)
from personalization.application.errors.file_error import (
    FileError,
    FileFailure,
)
from personalization.application.files.file_record import FileRecord, FileState
from personalization.application.previews.preview import (
    RenderedPreview,
    canvas_size,
    preview_id,
    preview_revision,
)
from personalization.application.previews.preview_worker import PreviewWorker
from personalization.application.templates.template_record import (
    Side,
    TemplateRecord,
)
from test.files.fakes import BUCKET
from test.previews.fakes import preview_data, renderer


@pytest.mark.parametrize(
    "failure", [None, "before-write", "after-write", "publish", "attach"]
)
def test_two_sided_recovery_is_immutable_and_does_not_modify_originals(
    failure: str | None,
) -> None:
    data = preview_data()
    source_bytes = dict(data.server.objects)
    repository = data.previews
    storage = data.server.adapter()
    worker = PreviewWorker(
        repository,
        data.analysis.templates,
        data.analysis.sources,
        storage,
        renderer(),
        BUCKET,
    )
    data.server.upload_failure = (
        failure if failure in ("before-write", "after-write") else None
    )
    repository.fail_publish = failure == "publish"
    repository.fail_attach = failure == "attach"
    try:
        if failure:
            with pytest.raises(FileError):
                worker.process(data.draft.id)
            assert data.designs.records[data.draft.id].front_preview_id is None
        data.server.upload_failure = None
        repository.fail_publish = repository.fail_attach = False
        assert worker.process(data.draft.id)
        saved = data.designs.records[data.draft.id]
        assert saved.version == data.draft.version
        assert preview_revision(saved) == preview_revision(data.draft)
        assert (
            len(repository.records) == 2
            and repository.candidates(None, 10) == []
        )
        uploads = sum(row.method == "POST" for row in data.server.requests)
        assert worker.process(data.draft.id)
        assert (
            sum(row.method == "POST" for row in data.server.requests)
            == uploads
        )
        for side in Side:
            image = repository.records[preview_id(saved, side)]
            assert (
                image.state is FileState.AVAILABLE
                and image.owner_id == saved.owner_id
            )
            with Image.open(
                BytesIO(data.server.objects[f"{BUCKET}/{image.object_key}"])
            ) as decoded:
                assert decoded.format == "PNG" and decoded.size == canvas_size(
                    data.analysis.template, side
                )
                assert not decoded.info
        for key, value in source_bytes.items():
            assert data.server.objects[key] == value
    finally:
        storage.close()


def test_concurrent_edit_rejects_old_previews_and_recovers() -> None:
    data = preview_data()
    storage = data.server.adapter()
    real_render = renderer()

    class RacingRenderer:
        def render(
            self,
            draft: DraftRecord,
            template: TemplateRecord,
            sources: tuple[ResolvedSource, ...],
            read: Callable[[FileRecord], bytes | None],
        ) -> tuple[RenderedPreview, RenderedPreview]:
            result = real_render.render(draft, template, sources, read)
            data.designs.update(
                draft.owner_id,
                draft.id,
                replace(draft.content, applications=()),
                DesignCondition(any_existing=True),
            )
            return result

    try:
        worker = PreviewWorker(
            data.previews,
            data.analysis.templates,
            data.analysis.sources,
            storage,
            RacingRenderer(),
            BUCKET,
        )
        assert worker.process(data.draft.id) is False
        changed = data.designs.records[data.draft.id]
        assert changed.front_preview_id is None and changed.version == 2
        assert preview_id(changed, Side.FRONT) != preview_id(
            data.draft, Side.FRONT
        )
        worker = PreviewWorker(
            data.previews,
            data.analysis.templates,
            data.analysis.sources,
            storage,
            real_render,
            BUCKET,
        )
        assert worker.process(data.draft.id)
        assert len(data.previews.records) == 4
    finally:
        storage.close()


def test_busy_frozen_missing_and_stopped_jobs_do_no_storage_io() -> None:
    data = preview_data()
    storage = data.server.adapter()
    worker = PreviewWorker(
        data.previews,
        data.analysis.templates,
        data.analysis.sources,
        storage,
        renderer(),
        BUCKET,
    )
    try:
        with data.previews.lock(data.draft.id):
            assert not worker.process(data.draft.id)
        assert worker.batch(None, 10, lambda: True).completed == 0
        data.designs.records[data.draft.id] = replace(
            data.draft, state=DesignState.FROZEN
        )
        assert not worker.process(data.draft.id) and not worker.process(
            uuid4()
        )
        assert not data.server.requests
    finally:
        storage.close()


def test_corrupt_pending_relation_and_wrong_bytes_are_rejected() -> None:
    data = preview_data()
    storage = data.server.adapter()
    worker = PreviewWorker(
        data.previews,
        data.analysis.templates,
        data.analysis.sources,
        storage,
        renderer(),
        BUCKET,
    )
    try:
        outputs = renderer().render(
            data.draft,
            data.analysis.template,
            data.analysis.sources.resolve(data.draft.content.applications),
            storage.read_verified,
        )
        record = outputs[0].record(data.draft, BUCKET)
        data.previews.records[record.id] = replace(record, owner_id=uuid4())
        with pytest.raises(FileError) as corrupt:
            worker.process(data.draft.id)
        assert corrupt.value.failure is FileFailure.FILE_INTEGRITY_MISMATCH
        data.previews.records.clear()
        data.server.objects[
            f"{BUCKET}/{data.analysis.sources.file.object_key}"
        ] = b"broken"
        batch = worker.batch(None, 10)
        assert batch.failures == ("FILE_INTEGRITY_MISMATCH",)
        assert batch.after == data.draft.id and batch.completed == 0
    finally:
        storage.close()
