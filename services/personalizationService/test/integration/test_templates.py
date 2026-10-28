"""Verify atomic draft versions and concurrency in real PostgreSQL."""

import os
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from decimal import Decimal
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

import personalization.infrastructure.database.template_repository as adapter
from personalization.application.errors.template_error import (
    TemplateError,
    TemplateFailure,
)
from personalization.application.prints.print_record import MAX_VERSION_NUMBER
from personalization.application.security.identity import (
    AppRole,
    VerifiedIdentity,
)
from personalization.application.templates.template_record import (
    Dimensions,
)
from personalization.application.templates.template_service import (
    TemplateService,
)
from personalization.bootstrap import create_app
from personalization.infrastructure.config.settings import Settings
from personalization.infrastructure.database.models.audit_entry import (
    AuditEntryModel,
)
from personalization.infrastructure.database.models.design import DesignModel
from personalization.infrastructure.database.models.template_version import (
    TemplateVersionModel,
)
from personalization.infrastructure.database.models.zone import ZoneModel
from personalization.infrastructure.database.models.zone_size import (
    ZoneSizeModel,
)
from personalization.infrastructure.database.template_repository import (
    SqlAlchemyTemplateRepository,
)
from test.security.conftest import claims as claims
from test.security.conftest import jwks_transport as jwks_transport
from test.security.conftest import sign_token as sign_token
from test.security.conftest import signing_keys as signing_keys
from test.security.test_print_http import Ready
from test.templates.fakes import definition, request_body

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("PERSONALIZATION_DATABASE_INTEGRATION") != "1",
        reason="Requires the disposable PostgreSQL integration database",
    ),
]


@dataclass(frozen=True)
class Series:
    actor_id: UUID
    product_id: UUID


@pytest.fixture
def series(engine: Engine) -> Iterator[Series]:
    seed = Series(uuid4(), uuid4())
    try:
        yield seed
    finally:
        with Session(engine) as session, session.begin():
            templates = select(TemplateVersionModel.id).where(
                TemplateVersionModel.product_id == seed.product_id
            )
            zones = select(ZoneModel.id).where(
                ZoneModel.template_id.in_(templates)
            )
            session.execute(
                delete(AuditEntryModel).where(
                    AuditEntryModel.actor_id == seed.actor_id
                )
            )
            session.execute(
                delete(DesignModel).where(
                    DesignModel.template_id.in_(templates)
                )
            )
            session.execute(
                delete(ZoneSizeModel).where(ZoneSizeModel.zone_id.in_(zones))
            )
            session.execute(
                delete(ZoneModel).where(ZoneModel.template_id.in_(templates))
            )
            session.execute(
                delete(TemplateVersionModel).where(
                    TemplateVersionModel.product_id == seed.product_id
                )
            )


def test_geometry_and_spanish_sql_values_are_persisted_atomically(
    engine: Engine, series: Series
) -> None:
    repository = SqlAlchemyTemplateRepository(engine)
    first = repository.create(
        series.actor_id, series.product_id, 1, 0, definition()
    )
    read = repository.get(first.header.id)
    assert read == first and read.header.active is False
    with Session(engine) as session:
        zone = session.get(ZoneModel, first.zones[0].id)
        size = session.get(ZoneSizeModel, first.zones[0].sizes[0].id)
        assert (
            zone is not None
            and zone.side == "FRENTE"
            and zone.x_mm == Decimal("50")
        )
        assert (
            size is not None
            and size.label == "CHICO"
            and size.surcharge_cents == 1250
        )
        audit = session.scalar(
            select(AuditEntryModel).where(
                AuditEntryModel.resource_id == first.header.id
            )
        )
        assert audit is not None and audit.actor_id == series.actor_id
        assert audit.action == "TEMPLATE_VERSION_CREATED"
        assert audit.detail == {
            "productId": str(series.product_id),
            "sizeId": 1,
            "versionNumber": 1,
            "zoneCount": 1,
            "sizeCount": 1,
            "active": False,
            "catalogValidation": "PENDING",
        }
    assert repository.list(series.product_id, 1, None, 20) == (first.header,)


def test_new_version_keeps_old_geometry_sizes_and_design_reference(
    engine: Engine, series: Series
) -> None:
    repository = SqlAlchemyTemplateRepository(engine)
    first = repository.create(
        series.actor_id, series.product_id, 1, 0, definition()
    )
    design_id = uuid4()
    with Session(engine) as session, session.begin():
        session.add(
            DesignModel(
                id=design_id,
                user_id=series.actor_id,
                variant_id=uuid4(),
                template_id=first.header.id,
                state="CONGELADO",
                version=1,
            )
        )
    updated = replace(
        definition(), front=Dimensions(Decimal("450"), Decimal("650"))
    )
    second = repository.create(
        series.actor_id, series.product_id, 1, 1, updated
    )
    assert first.header.id != second.header.id and second.header.number == 2
    assert first.zones[0].id != second.zones[0].id
    assert first.zones[0].sizes[0].id != second.zones[0].sizes[0].id
    assert repository.get(first.header.id) == first
    with Session(engine) as session:
        design = session.get(DesignModel, design_id)
        assert design is not None and design.template_id == first.header.id
    assert repository.list(series.product_id, 1, 1, 20) == (second.header,)
    assert repository.list(series.product_id, 2, None, 20) == ()


@pytest.mark.parametrize("initial_version", [0, 1])
def test_concurrent_creations_allow_one_successor(
    engine: Engine, series: Series, initial_version: int
) -> None:
    repository = SqlAlchemyTemplateRepository(engine)
    if initial_version:
        repository.create(
            series.actor_id, series.product_id, 1, 0, definition()
        )
    barrier = Barrier(2)

    def create() -> int | TemplateFailure:
        barrier.wait(timeout=10)
        try:
            return (
                SqlAlchemyTemplateRepository(engine)
                .create(
                    series.actor_id,
                    series.product_id,
                    1,
                    initial_version,
                    definition(),
                )
                .header.number
            )
        except TemplateError as error:
            return error.failure

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(create), pool.submit(create)]
        outcomes = [future.result(timeout=15) for future in futures]
    assert outcomes.count(initial_version + 1) == 1
    assert outcomes.count(TemplateFailure.TEMPLATE_VERSION_CONFLICT) == 1
    assert (
        len(repository.list(series.product_id, 1, None, 20))
        == initial_version + 1
    )


def test_audit_failure_rolls_back_flushed_template_zones_and_sizes(
    engine: Engine,
    series: Series,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collision_id = uuid4()
    with Session(engine) as session, session.begin():
        session.add(
            AuditEntryModel(
                id=collision_id,
                actor_id=series.actor_id,
                action="TEST_COLLISION",
                resource="plantilla_version",
                resource_id=series.product_id,
            )
        )
    original = AuditEntryModel

    def collided_audit(**values: object) -> AuditEntryModel:
        values["id"] = collision_id
        return original(**values)

    monkeypatch.setattr(adapter, "AuditEntryModel", collided_audit)
    with pytest.raises(TemplateError) as error:
        SqlAlchemyTemplateRepository(engine).create(
            series.actor_id, series.product_id, 1, 0, definition()
        )
    assert error.value.failure is TemplateFailure.TEMPLATE_DATABASE_UNAVAILABLE
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(TemplateVersionModel)
                .where(TemplateVersionModel.product_id == series.product_id)
            )
            == 0
        )
        assert session.scalar(select(func.count()).select_from(ZoneModel)) == 0
        assert (
            session.scalar(select(func.count()).select_from(ZoneSizeModel))
            == 0
        )
        assert session.get(AuditEntryModel, collision_id) is not None


def test_invalid_geometry_writes_nothing(
    engine: Engine, series: Series
) -> None:
    value = definition()
    zone = replace(value.zones[0], x_mm=Decimal("201"))
    service = TemplateService(SqlAlchemyTemplateRepository(engine))
    with pytest.raises(TemplateError) as error:
        service.create(
            VerifiedIdentity(series.actor_id, AppRole.ADMINISTRATOR),
            series.product_id,
            1,
            0,
            replace(value, zones=(zone,)),
        )
    assert error.value.failure is TemplateFailure.ZONE_OUTSIDE_TEMPLATE
    assert (
        service.list(
            VerifiedIdentity(series.actor_id, AppRole.ADMINISTRATOR),
            series.product_id,
            1,
        ).items
        == ()
    )


def test_unknown_and_corrupted_templates_fail_safely(
    engine: Engine, series: Series
) -> None:
    repository = SqlAlchemyTemplateRepository(engine)
    with pytest.raises(TemplateError) as missing:
        repository.get(uuid4())
    assert missing.value.failure is TemplateFailure.TEMPLATE_NOT_FOUND
    with Session(engine) as session, session.begin():
        row = TemplateVersionModel(
            id=uuid4(),
            product_id=series.product_id,
            size_id=1,
            number=1,
            front_width_mm=400,
            front_height_mm=600,
            back_width_mm=400,
            back_height_mm=600,
            active=False,
        )
        session.add(row)
        row_id = row.id
    with pytest.raises(TemplateError) as corrupt:
        repository.get(row_id)
    assert (
        corrupt.value.failure is TemplateFailure.TEMPLATE_DATABASE_UNAVAILABLE
    )


def test_version_limit_is_reported_without_overflow(
    engine: Engine, series: Series
) -> None:
    repository = SqlAlchemyTemplateRepository(engine)
    created = repository.create(
        series.actor_id, series.product_id, 1, 0, definition()
    )
    with Session(engine) as session, session.begin():
        row = session.get(TemplateVersionModel, created.header.id)
        assert row is not None
        row.number = MAX_VERSION_NUMBER
    with pytest.raises(TemplateError) as error:
        repository.create(
            series.actor_id,
            series.product_id,
            1,
            MAX_VERSION_NUMBER,
            definition(),
        )
    assert error.value.failure is TemplateFailure.TEMPLATE_VERSION_LIMIT


def test_http_with_postgres_signed_admin_and_client_rejection(
    engine: Engine,
    settings: Settings,
    series: Series,
    sign_token: Callable[..., str],
    claims: dict[str, object],
    jwks_transport: object,
) -> None:
    app = create_app(
        settings,
        Ready(),
        template_repository=SqlAlchemyTemplateRepository(engine),
    )
    payload = {
        **claims,
        "sub": str(series.actor_id),
        "app_metadata": {"app_role": "administrador"},
    }
    headers = {"Authorization": "Bearer " + sign_token(payload)}
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/admin/template-versions",
            headers=headers,
            json=request_body(series.product_id),
        )
        assert created.status_code == 201
        assert created.json()["active"] is False
        assert (
            client.get(created.headers["Location"], headers=headers).json()
            == created.json()
        )
        denied = client.get(
            created.headers["Location"],
            headers={"Authorization": "Bearer " + sign_token(claims)},
        )
        assert (
            denied.status_code == 403 and denied.json()["code"] == "FORBIDDEN"
        )
