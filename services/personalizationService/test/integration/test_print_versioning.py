"""Verify version serialization, historical files and atomic audit."""

import os
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from hashlib import sha256
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

import personalization.infrastructure.database.print_repository as adapter
from personalization.application.errors.print_error import (
    PrintError,
    PrintFailure,
)
from personalization.application.prints.print_record import PrintVersion
from personalization.bootstrap import create_app
from personalization.infrastructure.config.settings import Settings
from personalization.infrastructure.database.models.audit_entry import (
    AuditEntryModel,
)
from personalization.infrastructure.database.models.image_file import FileModel
from personalization.infrastructure.database.models.print import PrintModel
from personalization.infrastructure.database.models.print_version import (
    PrintVersionModel,
)
from personalization.infrastructure.database.print_repository import (
    SqlAlchemyPrintRepository,
)
from test.files.fakes import BUCKET
from test.image_samples import make_image
from test.security.conftest import claims as claims
from test.security.conftest import jwks_transport as jwks_transport
from test.security.conftest import sign_token as sign_token
from test.security.conftest import signing_keys as signing_keys

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("PERSONALIZATION_DATABASE_INTEGRATION") != "1",
        reason="Requires the disposable PostgreSQL integration database",
    ),
]


@dataclass(frozen=True)
class Seed:
    actor: UUID
    file_id: UUID

    @property
    def name(self) -> str:
        return str(self.actor)


@pytest.fixture
def seed(engine: Engine) -> Iterator[Seed]:
    data = Seed(uuid4(), uuid4())
    content = make_image()
    with Session(engine) as session, session.begin():
        session.add(
            FileModel(
                id=data.file_id,
                owner_id=data.actor,
                bucket=BUCKET,
                object_key=f"{data.file_id}.png",
                sha256=sha256(content).hexdigest(),
                mime_type="image/png",
                size_bytes=len(content),
                width_px=12,
                height_px=8,
                usage="ORIGINAL",
                state="DISPONIBLE",
            )
        )
    try:
        yield data
    finally:
        with Session(engine) as session, session.begin():
            ids = select(PrintModel.id).where(
                PrintModel.name.startswith(data.name)
            )
            session.execute(
                delete(AuditEntryModel).where(
                    (AuditEntryModel.actor_id == data.actor)
                    | AuditEntryModel.resource_id.in_(ids)
                )
            )
            session.execute(
                delete(PrintVersionModel).where(
                    PrintVersionModel.print_id.in_(ids)
                )
            )
            session.execute(
                delete(PrintModel).where(PrintModel.name.startswith(data.name))
            )
            session.execute(
                delete(FileModel).where(FileModel.owner_id == data.actor)
            )


def test_committed_versions_keep_original_price_file_and_audit(
    engine: Engine,
    seed: Seed,
) -> None:
    repository = SqlAlchemyPrintRepository(engine, BUCKET)
    created = repository.create(seed.actor, seed.name, None, seed.file_id, 0)
    second = repository.create_version(
        seed.actor, created.id, 1, seed.file_id, 2000
    )
    assert second.number == 2 and second.id != created.latest_version.id
    assert repository.get(created.id).latest_version == second
    assert repository.get_version(created.id, created.latest_version.id) == (
        created.latest_version
    )
    assert repository.list_versions(created.id, None, 20) == (
        created.latest_version,
        second,
    )
    assert repository.list_versions(created.id, 1, 20) == (second,)
    with Session(engine) as session:
        audit = session.scalars(
            select(AuditEntryModel)
            .where(AuditEntryModel.resource_id == created.id)
            .order_by(AuditEntryModel.created_at)
        ).all()
        assert [entry.action for entry in audit] == [
            "PRINT_CREATED",
            "PRINT_VERSION_CREATED",
        ]
        assert all(entry.actor_id == seed.actor for entry in audit)
        assert audit[0].detail == {
            "versionId": str(created.latest_version.id),
            "versionNumber": 1,
            "fileId": str(seed.file_id),
            "surchargeCents": 0,
            "currency": "MXN",
        }
        assert session.get(FileModel, seed.file_id) is not None


@pytest.mark.parametrize(
    "attribute,value",
    [
        ("state", "PENDIENTE_CARGA"),
        ("usage", "PREVIEW"),
        ("bucket", "other-bucket"),
    ],
)
def test_unusable_original_rolls_back_without_any_audit(
    engine: Engine,
    seed: Seed,
    attribute: str,
    value: str,
) -> None:
    repository = SqlAlchemyPrintRepository(engine, BUCKET)
    with Session(engine) as session, session.begin():
        file = session.get(FileModel, seed.file_id)
        assert file is not None
        setattr(file, attribute, value)
    with pytest.raises(PrintError) as caught:
        repository.create(seed.actor, seed.name, None, seed.file_id, 100)
    assert caught.value.failure is PrintFailure.INVALID_PRINT_FILE
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(PrintModel)
                .where(PrintModel.name == seed.name)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditEntryModel)
                .where(AuditEntryModel.actor_id == seed.actor)
            )
            == 0
        )


def test_missing_file_and_unknown_resource_have_stable_failures(
    engine: Engine,
    seed: Seed,
) -> None:
    repository = SqlAlchemyPrintRepository(engine, BUCKET)
    with pytest.raises(PrintError) as caught:
        repository.create(seed.actor, seed.name, None, uuid4(), 0)
    assert caught.value.failure is PrintFailure.PRINT_FILE_NOT_FOUND
    with pytest.raises(PrintError) as missing:
        repository.get(uuid4())
    assert missing.value.failure is PrintFailure.PRINT_NOT_FOUND
    with pytest.raises(PrintError):
        repository.create_version(seed.actor, uuid4(), 1, seed.file_id, 0)
    with pytest.raises(PrintError):
        repository.list_versions(uuid4(), None, 20)
    with pytest.raises(PrintError) as version:
        repository.get_version(uuid4(), uuid4())
    assert version.value.failure is PrintFailure.PRINT_VERSION_NOT_FOUND


def test_two_writers_create_only_one_successor(
    engine: Engine,
    seed: Seed,
) -> None:
    repository = SqlAlchemyPrintRepository(engine, BUCKET)
    created = repository.create(seed.actor, seed.name, None, seed.file_id, 0)
    barrier = Barrier(2)

    def write(cost: int) -> PrintVersion | PrintFailure:
        barrier.wait(timeout=5)
        try:
            return repository.create_version(
                seed.actor, created.id, 1, seed.file_id, cost
            )
        except PrintError as error:
            return error.failure

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, (1500, 2000)))
    assert sum(isinstance(result, PrintVersion) for result in results) == 1
    assert results.count(PrintFailure.PRINT_VERSION_CONFLICT) == 1
    versions = repository.list_versions(created.id, None, 20)
    assert [row.number for row in versions] == [1, 2]
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditEntryModel)
                .where(AuditEntryModel.resource_id == created.id)
            )
            == 2
        )


@pytest.mark.parametrize("operation", ["create", "version"])
def test_audit_constraint_failure_rolls_back_business_rows(
    engine: Engine,
    seed: Seed,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    repository = SqlAlchemyPrintRepository(engine, BUCKET)
    created = repository.create(seed.actor, seed.name, None, seed.file_id, 100)
    marker = uuid4()
    with Session(engine) as session, session.begin():
        session.add(
            AuditEntryModel(
                id=marker,
                actor_id=seed.actor,
                action="TEST_MARKER",
                resource="test",
                resource_id=uuid4(),
                detail=None,
            )
        )
    # Force a real PostgreSQL audit PK violation after business flushes.
    monkeypatch.setattr(adapter, "uuid4", lambda: marker)
    with pytest.raises(PrintError) as caught:
        if operation == "create":
            repository.create(
                seed.actor, seed.name + "-failed", None, seed.file_id, 200
            )
        else:
            repository.create_version(
                seed.actor, created.id, 1, seed.file_id, 200
            )
    assert caught.value.failure is PrintFailure.PRINT_DATABASE_UNAVAILABLE
    assert "TEST_MARKER" not in str(caught.value)
    assert len(repository.list_versions(created.id, None, 20)) == 1
    with Session(engine) as session:
        assert session.get(PrintModel, marker) is None
        assert session.get(PrintVersionModel, marker) is None
        assert session.get(AuditEntryModel, marker) is not None
    monkeypatch.undo()
    assert (
        repository.create_version(
            seed.actor, created.id, 1, seed.file_id, 200
        ).number
        == 2
    )


def test_latest_version_join_and_keyset_pagination(
    engine: Engine,
    seed: Seed,
) -> None:
    repository = SqlAlchemyPrintRepository(engine, BUCKET)
    created = [
        repository.create(
            seed.actor, seed.name + str(i), None, seed.file_id, i
        )
        for i in range(3)
    ]
    updated = repository.create_version(
        seed.actor, created[0].id, 1, seed.file_id, 500
    )
    records = repository.list(None, 100)
    expected = sorted(row.id for row in created)
    assert [row.id for row in records] == expected
    assert (
        next(row for row in records if row.id == created[0].id).latest_version
        == updated
    )
    first = repository.list(None, 2)
    second = repository.list(first[-1].id, 2)
    assert [row.id for row in first + second] == expected


def test_version_overflow_keeps_existing_history(
    engine: Engine,
    seed: Seed,
) -> None:
    repository = SqlAlchemyPrintRepository(engine, BUCKET)
    created = repository.create(seed.actor, seed.name, None, seed.file_id, 0)
    with Session(engine) as session, session.begin():
        row = session.get(PrintVersionModel, created.latest_version.id)
        assert row is not None
        row.number = 2_147_483_647
    with pytest.raises(PrintError) as caught:
        repository.create_version(
            seed.actor, created.id, 2_147_483_647, seed.file_id, 100
        )
    assert caught.value.failure is PrintFailure.PRINT_VERSION_LIMIT
    assert len(repository.list_versions(created.id, None, 20)) == 1


def test_version_from_another_print_is_not_addressable(
    engine: Engine,
    seed: Seed,
) -> None:
    repository = SqlAlchemyPrintRepository(engine, BUCKET)
    first = repository.create(seed.actor, seed.name, None, seed.file_id, 0)
    second = repository.create(
        seed.actor, seed.name + "-second", None, seed.file_id, 0
    )
    with pytest.raises(PrintError) as caught:
        repository.get_version(first.id, second.latest_version.id)
    assert caught.value.failure is PrintFailure.PRINT_VERSION_NOT_FOUND


def test_http_workflow_with_real_postgres_jwt_and_atomic_audit(
    engine: Engine,
    seed: Seed,
    settings: Settings,
    sign_token: Callable[..., str],
    claims: dict[str, object],
    jwks_transport: object,
) -> None:
    payload = {**claims, "app_metadata": {"app_role": "administrador"}}
    token = sign_token(payload)
    headers = {"Authorization": "Bearer " + token, "X-User-ID": str(uuid4())}
    base = "/api/v1/admin/prints"
    with TestClient(create_app(settings)) as client:
        created = client.post(
            base,
            headers=headers,
            json={
                "name": seed.name,
                "fileId": str(seed.file_id),
                "surchargeCents": 1500,
            },
        )
        assert created.status_code == 201
        resource = created.headers["Location"]
        original_version = created.json()["latestVersion"]
        request = {
            "expectedVersion": 1,
            "fileId": str(seed.file_id),
            "surchargeCents": 2000,
        }
        version = client.post(
            resource + "/versions", headers=headers, json=request
        )
        assert version.status_code == 201
        assert (
            client.get(version.headers["Location"], headers=headers).json()
            == version.json()
        )
        assert (
            client.get(resource, headers=headers).json()["latestVersion"]
            == version.json()
        )
        first = client.get(
            resource + "/versions", headers=headers, params={"limit": 1}
        ).json()
        assert first["items"] == [original_version]
        second = client.get(
            resource + "/versions",
            headers=headers,
            params={"limit": 1, "cursor": first["nextCursor"]},
        ).json()
        assert second["items"] == [version.json()]
        assert second["nextCursor"] is None
        conflict = client.post(
            resource + "/versions", headers=headers, json=request
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "PRINT_VERSION_CONFLICT"
        assert client.get(base).status_code == 401
        customer = client.get(
            base,
            headers={
                "Authorization": "Bearer " + sign_token(),
            },
        )
        assert customer.status_code == 403
    with Session(engine) as session:
        audit = session.scalars(
            select(AuditEntryModel).where(
                AuditEntryModel.resource_id == UUID(created.json()["id"])
            )
        ).all()
        assert len(audit) == 2
        assert all(
            str(entry.actor_id) == str(claims["sub"]) for entry in audit
        )
