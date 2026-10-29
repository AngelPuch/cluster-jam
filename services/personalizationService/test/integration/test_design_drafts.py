"""Check draft transactions in disposable PostgreSQL."""

import os
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

import personalization.infrastructure.database.design_repository as adapter
from personalization.application.designs.analysis_record import (
    AnalysisSelection,
)
from personalization.application.designs.draft_record import (
    DesignCondition,
    DesignState,
    DraftContent,
    DraftRecord,
    draft_revision,
)
from personalization.application.errors.design_analysis_error import (
    AnalysisFailure,
    DesignAnalysisError,
)
from personalization.application.errors.design_error import (
    DesignError,
    DesignFailure,
)
from personalization.application.errors.security_error import SecurityError
from personalization.application.prints.print_record import MAX_VERSION_NUMBER
from personalization.bootstrap import create_app
from personalization.infrastructure.config.settings import Settings
from personalization.infrastructure.database.design_repository import (
    SqlAlchemyDesignRepository,
)
from personalization.infrastructure.database.models.application import (
    ApplicationModel,
)
from personalization.infrastructure.database.models.audit_entry import (
    AuditEntryModel,
)
from personalization.infrastructure.database.models.design import DesignModel
from personalization.infrastructure.database.models.image_file import FileModel
from personalization.infrastructure.database.print_repository import (
    SqlAlchemyPrintRepository,
)
from personalization.infrastructure.database.template_repository import (
    SqlAlchemyTemplateRepository,
)
from test.files.fakes import BUCKET
from test.integration.test_print_versioning import Seed
from test.integration.test_print_versioning import seed as seed
from test.integration.test_templates import Series
from test.integration.test_templates import series as series
from test.security.conftest import claims as claims
from test.security.conftest import jwks_transport as jwks_transport
from test.security.conftest import sign_token as sign_token
from test.security.conftest import signing_keys as signing_keys
from test.security.test_print_http import Ready
from test.templates.fakes import definition

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("PERSONALIZATION_DATABASE_INTEGRATION") != "1",
        reason="Requires the disposable PostgreSQL integration database",
    ),
]


@dataclass(frozen=True)
class DraftSeed:
    owner_id: UUID
    content: DraftContent


@pytest.fixture
def draft_seed(
    engine: Engine, series: Series, seed: Seed
) -> Iterator[DraftSeed]:
    template = SqlAlchemyTemplateRepository(engine).create(
        series.actor_id, series.product_id, 1, 0, definition()
    )
    printed = SqlAlchemyPrintRepository(engine, BUCKET).create(
        seed.actor, seed.name, None, seed.file_id, 100
    )
    selection = AnalysisSelection(
        template.zones[0].id,
        template.zones[0].sizes[0].id,
        printed.latest_version.id,
        None,
    )
    value = DraftSeed(
        series.actor_id,
        DraftContent(uuid4(), template.header.id, (selection,)),
    )
    try:
        yield value
    finally:
        # Remove our children before parent fixtures clean up.
        with Session(engine) as session, session.begin():
            designs = select(DesignModel.id).where(
                DesignModel.user_id == value.owner_id
            )
            session.execute(
                delete(ApplicationModel).where(
                    ApplicationModel.design_id.in_(designs)
                )
            )
            session.execute(
                delete(DesignModel).where(
                    DesignModel.user_id == value.owner_id
                )
            )


def condition(record: DraftRecord) -> DesignCondition:
    return DesignCondition(frozenset({draft_revision(record)}))


def audits(engine: Engine, owner: UUID) -> int:
    with Session(engine) as session:
        return (
            session.scalar(
                select(func.count())
                .select_from(AuditEntryModel)
                .where(
                    AuditEntryModel.actor_id == owner,
                    AuditEntryModel.resource == "diseno",
                )
            )
            or 0
        )


def test_committed_snapshot_noop_clear_and_independent_copy(
    engine: Engine, draft_seed: DraftSeed, seed: Seed
) -> None:
    repo = SqlAlchemyDesignRepository(engine, BUCKET)
    data = draft_seed
    first = repo.create(data.owner_id, data.content)
    assert repo.get(data.owner_id, first.id) == first
    assert first.version == 1 and first.state is DesignState.DRAFT
    with Session(engine) as session, session.begin():
        row = session.get(DesignModel, first.id)
        assert row is not None
        row.front_preview_id = seed.file_id
        row.back_preview_id = seed.file_id
    decorated = repo.get(data.owner_id, first.id)
    same = repo.update(
        data.owner_id, first.id, data.content, condition(decorated)
    )
    assert same == decorated and audits(engine, data.owner_id) == 1
    copied = repo.copy(data.owner_id, first.id)
    assert copied.id != first.id and copied.content == first.content
    assert copied.applications[0].id != first.applications[0].id
    assert copied.front_preview_id is None and copied.back_preview_id is None
    updated = repo.update(
        data.owner_id,
        first.id,
        replace(data.content, applications=()),
        condition(decorated),
    )
    assert updated.version == 2 and updated.applications == ()
    assert updated.front_preview_id is None and updated.back_preview_id is None
    assert repo.get(data.owner_id, copied.id) == copied
    assert audits(engine, data.owner_id) == 3
    with Session(engine) as session:
        assert session.get(ApplicationModel, first.applications[0].id) is None
        audit = session.scalar(
            select(AuditEntryModel).where(
                AuditEntryModel.resource_id == copied.id
            )
        )
        assert audit is not None and audit.action == "DESIGN_DRAFT_COPIED"
        assert audit.detail is not None
        assert audit.detail["sourceDesignId"] == str(first.id)
        assert audit.detail["catalogValidation"] == "PENDING"


def test_two_simultaneous_replacements_allow_one_revision(
    engine: Engine, draft_seed: DraftSeed
) -> None:
    data = draft_seed
    repo = SqlAlchemyDesignRepository(engine, BUCKET)
    first = repo.create(data.owner_id, data.content)
    barrier = Barrier(2)

    def change() -> int | DesignFailure:
        barrier.wait(timeout=10)
        try:
            return (
                SqlAlchemyDesignRepository(engine, BUCKET)
                .update(
                    data.owner_id,
                    first.id,
                    replace(data.content, variant_id=uuid4()),
                    condition(first),
                )
                .version
            )
        except DesignError as error:
            return error.failure

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: change(), range(2)))
    assert results.count(2) == 1
    assert results.count(DesignFailure.DESIGN_PRECONDITION_FAILED) == 1
    assert repo.get(data.owner_id, first.id).version == 2
    assert audits(engine, data.owner_id) == 2


@pytest.mark.parametrize("operation", ["create", "update", "copy"])
def test_audit_failure_rolls_back_root_children_and_revision(
    engine: Engine,
    draft_seed: DraftSeed,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    data = draft_seed
    repo = SqlAlchemyDesignRepository(engine, BUCKET)
    first = repo.create(data.owner_id, data.content)
    with Session(engine) as session:
        collision = session.scalar(
            select(AuditEntryModel.id).where(
                AuditEntryModel.resource_id == first.id
            )
        )
    assert collision is not None
    factory = AuditEntryModel

    def broken_audit(**values: object) -> AuditEntryModel:
        values["id"] = collision
        return factory(**values)

    monkeypatch.setattr(adapter, "AuditEntryModel", broken_audit)
    with pytest.raises(DesignError) as error:
        if operation == "create":
            repo.create(data.owner_id, data.content)
        elif operation == "update":
            repo.update(
                data.owner_id,
                first.id,
                replace(data.content, applications=()),
                condition(first),
            )
        else:
            repo.copy(data.owner_id, first.id)
    assert error.value.failure is DesignFailure.DESIGN_DATABASE_UNAVAILABLE
    assert repo.get(data.owner_id, first.id) == first
    assert repo.list(data.owner_id, None, 100) == (
        replace(first, applications=()),
    )
    assert audits(engine, data.owner_id) == 1


def test_ownership_frozen_copy_and_version_exhaustion(
    engine: Engine, draft_seed: DraftSeed
) -> None:
    data = draft_seed
    repo = SqlAlchemyDesignRepository(engine, BUCKET)
    first = repo.create(data.owner_id, data.content)
    stranger = uuid4()
    operations: tuple[Callable[[], DraftRecord], ...] = (
        lambda: repo.get(stranger, first.id),
        lambda: repo.update(
            stranger, first.id, data.content, condition(first)
        ),
        lambda: repo.copy(stranger, first.id),
    )
    for operation in operations:
        with pytest.raises(SecurityError):
            operation()
    assert repo.list(stranger, None, 20) == ()
    with Session(engine) as session, session.begin():
        row = session.get(DesignModel, first.id)
        assert row is not None
        row.version = MAX_VERSION_NUMBER
    capped = repo.get(data.owner_id, first.id)
    assert (
        repo.update(data.owner_id, first.id, data.content, condition(capped))
        == capped
    )
    with pytest.raises(DesignError) as exhausted:
        repo.update(
            data.owner_id,
            first.id,
            replace(data.content, applications=()),
            condition(capped),
        )
    assert exhausted.value.failure is DesignFailure.DESIGN_VERSION_LIMIT
    with Session(engine) as session, session.begin():
        row = session.get(DesignModel, first.id)
        assert row is not None
        row.state = "CONGELADO"
    frozen = repo.get(data.owner_id, first.id)
    with pytest.raises(DesignError) as immutable:
        repo.update(data.owner_id, first.id, data.content, condition(frozen))
    assert immutable.value.failure is DesignFailure.DESIGN_NOT_EDITABLE
    copied = repo.copy(data.owner_id, first.id)
    assert copied.id != first.id and copied.version == 1
    assert (
        copied.state is DesignState.DRAFT and copied.content == frozen.content
    )
    assert repo.get(data.owner_id, first.id) == frozen


@pytest.mark.parametrize(
    "invalid", ["zone", "size", "duplicate", "both", "missing"]
)
def test_rechecks_bindings_inside_write_transaction(
    engine: Engine, draft_seed: DraftSeed, invalid: str, seed: Seed
) -> None:
    data = draft_seed
    chosen = data.content.applications[0]
    choices: tuple[AnalysisSelection, ...] = (chosen,)
    if invalid == "zone":
        choices = (replace(chosen, zone_id=uuid4()),)
    elif invalid == "size":
        choices = (replace(chosen, zone_size_id=uuid4()),)
    elif invalid == "duplicate":
        choices = (chosen, chosen)
    elif invalid == "both":
        choices = (replace(chosen, file_id=seed.file_id),)
    else:
        choices = (replace(chosen, print_version_id=None),)
    repo = SqlAlchemyDesignRepository(engine, BUCKET)
    with pytest.raises(DesignError) as error:
        repo.create(data.owner_id, replace(data.content, applications=choices))
    assert error.value.failure is DesignFailure.INVALID_DESIGN_DATA
    assert repo.list(data.owner_id, None, 20) == ()
    assert audits(engine, data.owner_id) == 0


@pytest.mark.parametrize(
    "source", ["unknown", "pending", "thumbnail", "bucket"]
)
def test_non_original_or_unavailable_source_never_leaves_a_draft(
    engine: Engine, draft_seed: DraftSeed, seed: Seed, source: str
) -> None:
    data = draft_seed
    with Session(engine) as session, session.begin():
        row = session.get(FileModel, seed.file_id)
        assert row is not None
        if source == "pending":
            row.state = "PENDIENTE_CARGA"
        elif source == "thumbnail":
            row.usage = "MINIATURA_V1:" + str(uuid4())
        elif source == "bucket":
            row.bucket = "another-private-bucket"
    chosen = replace(
        data.content.applications[0],
        print_version_id=None,
        file_id=uuid4() if source == "unknown" else seed.file_id,
    )
    repo = SqlAlchemyDesignRepository(engine, BUCKET)
    with pytest.raises(DesignAnalysisError) as error:
        repo.create(
            data.owner_id, replace(data.content, applications=(chosen,))
        )
    assert error.value.failure is (
        AnalysisFailure.ANALYSIS_SOURCE_NOT_FOUND
        if source == "unknown"
        else AnalysisFailure.ANALYSIS_SOURCE_NOT_READY
    )
    assert repo.list(data.owner_id, None, 20) == ()
    assert audits(engine, data.owner_id) == 0


def test_http_signed_jwt_and_postgresql_persistence(
    engine: Engine,
    settings: Settings,
    draft_seed: DraftSeed,
    sign_token: Callable[..., str],
    claims: dict[str, object],
    jwks_transport: object,
) -> None:
    data = draft_seed
    app = create_app(
        settings,
        Ready(),
        template_repository=SqlAlchemyTemplateRepository(engine),
        design_repository=SqlAlchemyDesignRepository(engine, BUCKET),
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
    chosen = data.content.applications[0]
    body = {
        "variantId": str(data.content.variant_id),
        "templateId": str(data.content.template_id),
        "applications": [
            {
                "zoneId": str(chosen.zone_id),
                "zoneSizeId": str(chosen.zone_size_id),
                "printVersionId": str(chosen.print_version_id),
            }
        ],
    }
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/admin/design-drafts", headers=headers, json=body
        )
        assert created.status_code == 201
        path = created.headers["Location"]
        read = client.get(path, headers=headers)
        assert read.json() == created.json()
        assert read.headers["ETag"] == created.headers["ETag"]
        saved = client.put(
            path,
            headers={**headers, "If-Match": read.headers["ETag"]},
            json={**body, "applications": []},
        )
        assert saved.status_code == 200 and saved.json()["version"] == 2
        stale = client.put(
            path,
            headers={**headers, "If-Match": read.headers["ETag"]},
            json=body,
        )
        assert stale.status_code == 412
        copied = client.post(path + "/copies", headers=headers)
        assert (
            copied.status_code == 201 and copied.json()["applications"] == []
        )
        assert client.get(path, headers=headers).json() == saved.json()
    assert audits(engine, data.owner_id) == 3
