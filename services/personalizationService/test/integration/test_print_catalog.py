"""Verify current catalog visibility with real PostgreSQL queries."""

import os
from collections.abc import Callable
from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from personalization.application.catalog.catalog_service import CatalogService
from personalization.application.errors.print_error import (
    PrintError,
    PrintFailure,
)
from personalization.application.files.file_record import FileRecord, FileState
from personalization.application.prints.print_changes import (
    PrintChanges,
    PrintCondition,
    print_revision,
)
from personalization.application.security.identity import (
    AppRole,
    VerifiedIdentity,
)
from personalization.bootstrap import create_app
from personalization.infrastructure.config.settings import Settings
from personalization.infrastructure.database.file_repository import (
    SqlAlchemyFileRepository,
)
from personalization.infrastructure.database.models.image_file import FileModel
from personalization.infrastructure.database.print_catalog_repository import (
    SqlAlchemyPrintCatalogRepository,
)
from personalization.infrastructure.database.print_repository import (
    SqlAlchemyPrintRepository,
)
from personalization.infrastructure.database.thumbnail_repository import (
    SqlAlchemyThumbnailRepository,
)
from test.files.fakes import BUCKET, StorageServer
from test.image_samples import make_image
from test.integration.test_print_versioning import Seed
from test.integration.test_print_versioning import seed as seed
from test.security.conftest import claims as claims
from test.security.conftest import jwks_transport as jwks_transport
from test.security.conftest import sign_token as sign_token
from test.security.conftest import signing_keys as signing_keys
from test.security.test_print_http import Ready
from test.thumbnails.test_thumbnail_worker import renderer

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("PERSONALIZATION_DATABASE_INTEGRATION") != "1",
        reason="Requires the disposable PostgreSQL integration database",
    ),
]


def publish_thumbnail(engine: Engine, file_id: UUID) -> FileRecord:
    source = SqlAlchemyFileRepository(engine).get(file_id)
    assert source is not None
    record = renderer().render(source, make_image()).record(source)
    repository = SqlAlchemyThumbnailRepository(engine, BUCKET)
    return repository.publish(repository.reserve(record))


def test_only_current_version_with_available_thumbnail_is_published(
    engine: Engine,
    seed: Seed,
) -> None:
    prints = SqlAlchemyPrintRepository(engine, BUCKET)
    created = prints.create(seed.actor, seed.name, None, seed.file_id, 1234)
    catalog = SqlAlchemyPrintCatalogRepository(engine, BUCKET)
    assert catalog.list(None, 20) == () and catalog.get(created.id) is None
    source = SqlAlchemyFileRepository(engine).get(seed.file_id)
    assert source is not None
    thumbnails = SqlAlchemyThumbnailRepository(engine, BUCKET)
    pending = renderer().render(source, make_image()).record(source)
    thumbnails.reserve(pending)
    assert catalog.get(created.id) is None
    thumbnails.publish(pending)
    row = catalog.get(created.id)
    assert row is not None and row.version_id == created.latest_version.id
    assert row.surcharge_cents == 1234 and row.thumbnail.id == pending.id
    second = prints.create_version(
        seed.actor, created.id, 1, seed.file_id, 4321
    )
    row = catalog.get(created.id)
    assert (
        row is not None
        and row.version_id == second.id
        and row.surcharge_cents == 4321
    )
    assert row.thumbnail.id == pending.id


def test_new_image_never_falls_back_to_previous_price_or_thumbnail(
    engine: Engine,
    seed: Seed,
) -> None:
    prints = SqlAlchemyPrintRepository(engine, BUCKET)
    created = prints.create(seed.actor, seed.name, None, seed.file_id, 10)
    publish_thumbnail(engine, seed.file_id)
    catalog = SqlAlchemyPrintCatalogRepository(engine, BUCKET)
    assert catalog.get(created.id) is not None
    files = SqlAlchemyFileRepository(engine)
    source = files.get(seed.file_id)
    assert source is not None
    new_id = uuid4()
    new_source = replace(
        source, id=new_id, object_key=f"{new_id}.png", state=FileState.PENDING
    )
    files.create_pending(new_source)
    files.make_available(new_id)
    new_version = prints.create_version(seed.actor, created.id, 1, new_id, 200)
    assert catalog.get(created.id) is None and catalog.list(None, 20) == ()
    publish_thumbnail(engine, new_id)
    visible = catalog.get(created.id)
    assert visible is not None and visible.version_id == new_version.id
    assert visible.surcharge_cents == 200
    assert visible.thumbnail.id != publish_thumbnail(engine, seed.file_id).id


def test_retirement_hides_detail_and_new_links_and_preserves_history(
    engine: Engine,
    seed: Seed,
) -> None:
    prints = SqlAlchemyPrintRepository(engine, BUCKET)
    created = prints.create(seed.actor, seed.name, None, seed.file_id, 0)
    publish_thumbnail(engine, seed.file_id)
    catalog = SqlAlchemyPrintCatalogRepository(engine, BUCKET)
    server = StorageServer()
    storage = server.adapter()
    service = CatalogService(catalog, storage, 60)
    customer = VerifiedIdentity(uuid4(), AppRole.CLIENT)
    try:
        assert (
            service.get(customer, created.id).version_id
            == created.latest_version.id
        )
        retired = prints.update(
            seed.actor,
            created.id,
            PrintChanges(frozenset({"active"}), active=False),
            PrintCondition(frozenset({print_revision(created)})),
        )
        assert service.list(customer).items == ()
        with pytest.raises(PrintError) as hidden:
            service.create_thumbnail_download(
                customer, created.id, created.latest_version.id
            )
        assert hidden.value.failure is PrintFailure.PRINT_NOT_FOUND
        assert not server.requests
        assert (
            prints.get_version(created.id, created.latest_version.id)
            == created.latest_version
        )
        prints.update(
            seed.actor,
            created.id,
            PrintChanges(frozenset({"active"}), active=True),
            PrintCondition(frozenset({print_revision(retired)})),
        )
        assert (
            service.get(customer, created.id).version_id
            == created.latest_version.id
        )
    finally:
        storage.close()


@pytest.mark.parametrize(
    "damage",
    [
        "original-pending",
        "original-bucket",
        "thumbnail-pending",
        "thumbnail-owner",
        "thumbnail-mime",
        "thumbnail-size",
        "thumbnail-usage",
    ],
)
def test_unusable_files_are_excluded_before_pagination(
    engine: Engine,
    seed: Seed,
    damage: str,
) -> None:
    prints = SqlAlchemyPrintRepository(engine, BUCKET)
    created = prints.create(seed.actor, seed.name, None, seed.file_id, 0)
    thumbnail = publish_thumbnail(engine, seed.file_id)
    with Session(engine) as session, session.begin():
        original = session.get(FileModel, seed.file_id)
        derived = session.get(FileModel, thumbnail.id)
        assert original is not None and derived is not None
        match damage:
            case "original-pending":
                original.state = "PENDIENTE_CARGA"
            case "original-bucket":
                original.bucket = "another-bucket"
            case "thumbnail-pending":
                derived.state = "PENDIENTE_CARGA"
            case "thumbnail-owner":
                derived.owner_id = UUID(int=0)
            case "thumbnail-mime":
                derived.mime_type = "image/jpeg"
            case "thumbnail-size":
                derived.width_px = 321
            case "thumbnail-usage":
                derived.usage = "PREVIEW"
    try:
        catalog = SqlAlchemyPrintCatalogRepository(engine, BUCKET)
        assert catalog.get(created.id) is None and catalog.list(None, 1) == ()
    finally:
        if damage == "thumbnail-owner":
            # Restore ownership for the fixture's targeted cleanup.
            with Session(engine) as session, session.begin():
                derived = session.get(FileModel, thumbnail.id)
                assert derived is not None
                derived.owner_id = seed.actor


def test_list_and_detail_each_use_one_query_with_exact_pagination(
    engine: Engine,
    seed: Seed,
) -> None:
    prints = SqlAlchemyPrintRepository(engine, BUCKET)
    ids = [
        prints.create(seed.actor, seed.name + str(i), None, seed.file_id, i).id
        for i in range(4)
    ]
    publish_thumbnail(engine, seed.file_id)
    catalog = SqlAlchemyPrintCatalogRepository(engine, BUCKET)
    queries: list[str] = []

    def track(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        queries.append(statement)

    event.listen(engine, "before_cursor_execute", track)
    try:
        first = catalog.list(None, 2)
        assert [row.id for row in first] == sorted(ids)[:2]
        assert len(queries) == 1
        second = catalog.list(first[-1].id, 2)
        assert [row.id for row in second] == sorted(ids)[2:]
        assert len(queries) == 2
        assert catalog.get(ids[0]) is not None
        assert len(queries) == 3
    finally:
        event.remove(engine, "before_cursor_execute", track)


def test_real_database_and_client_jwt_preserve_original_permissions(
    engine: Engine,
    settings: Settings,
    seed: Seed,
    sign_token: Callable[..., str],
    claims: dict[str, object],
    jwks_transport: object,
) -> None:
    prints = SqlAlchemyPrintRepository(engine, BUCKET)
    created = prints.create(seed.actor, seed.name, None, seed.file_id, 1250)
    thumbnail = publish_thumbnail(engine, seed.file_id)
    server = StorageServer()
    storage = server.adapter()
    app = create_app(
        settings,
        Ready(),
        file_repository=SqlAlchemyFileRepository(engine),
        print_repository=prints,
        thumbnail_repository=SqlAlchemyThumbnailRepository(engine, BUCKET),
        catalog_repository=SqlAlchemyPrintCatalogRepository(engine, BUCKET),
        storage=storage,
    )
    headers = {"Authorization": "Bearer " + sign_token(claims)}
    try:
        with TestClient(app) as client:
            detail = client.get(
                f"/api/v1/prints/{created.id}", headers=headers
            )
            assert detail.status_code == 200
            path = detail.json()["thumbnail"]["downloadUrlEndpoint"]
            link = client.post(path, headers=headers)
            assert link.status_code == 201 and link.json()["fileId"] == str(
                thumbnail.id
            )
            assert (
                client.get(
                    f"/api/v1/files/{seed.file_id}", headers=headers
                ).status_code
                == 403
            )
            assert (
                client.get("/api/v1/admin/prints", headers=headers).status_code
                == 403
            )
            # A new price version invalidates the former catalog link.
            prints.create_version(
                seed.actor, created.id, 1, seed.file_id, 2500
            )
            count = len(server.requests)
            assert client.post(path, headers=headers).status_code == 404
            assert len(server.requests) == count
    finally:
        storage.close()


@pytest.mark.parametrize("damage", ["money", "derived-id"])
def test_corrupt_identity_or_unsafe_json_money_fails_closed(
    engine: Engine,
    seed: Seed,
    damage: str,
) -> None:
    from personalization.application.prints.print_record import (
        MAX_SURCHARGE_CENTS,
    )
    from personalization.infrastructure.database.models.print_version import (
        PrintVersionModel,
    )

    prints = SqlAlchemyPrintRepository(engine, BUCKET)
    created = prints.create(seed.actor, seed.name, None, seed.file_id, 0)
    derived = publish_thumbnail(engine, seed.file_id)
    with Session(engine) as session, session.begin():
        if damage == "money":
            version = session.get(PrintVersionModel, created.latest_version.id)
            assert version is not None
            version.surcharge_cents = MAX_SURCHARGE_CENTS + 1
        else:
            thumbnail = session.get(FileModel, derived.id)
            assert thumbnail is not None
            thumbnail.id = uuid4()
            thumbnail.object_key = f"{thumbnail.id}.png"
    with pytest.raises(PrintError) as error:
        SqlAlchemyPrintCatalogRepository(engine, BUCKET).get(created.id)
    assert error.value.failure is PrintFailure.PRINT_DATABASE_UNAVAILABLE
