"""Exercise read-only calculations with real database references."""

import os
from collections.abc import Callable
from dataclasses import replace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, func, select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from personalization.application.designs.analysis_record import (
    AnalysisSelection,
)
from personalization.application.designs.design_analysis_service import (
    DesignAnalysisService,
)
from personalization.application.errors.design_analysis_error import (
    AnalysisFailure,
    DesignAnalysisError,
)
from personalization.application.prints.print_record import MAX_SURCHARGE_CENTS
from personalization.application.security.identity import (
    AppRole,
    VerifiedIdentity,
)
from personalization.application.templates.template_record import Side
from personalization.bootstrap import create_app
from personalization.infrastructure.config.settings import Settings
from personalization.infrastructure.database.analysis_repository import (
    SqlAlchemyAnalysisSourceRepository,
)
from personalization.infrastructure.database.models.application import (
    ApplicationModel,
)
from personalization.infrastructure.database.models.audit_entry import (
    AuditEntryModel,
)
from personalization.infrastructure.database.models.design import DesignModel
from personalization.infrastructure.database.models.image_file import FileModel
from personalization.infrastructure.database.models.print import PrintModel
from personalization.infrastructure.database.print_repository import (
    SqlAlchemyPrintRepository,
)
from personalization.infrastructure.database.template_repository import (
    SqlAlchemyTemplateRepository,
)
from personalization.infrastructure.images.image_geometry import (
    PillowImageGeometry,
)
from test.designs.fakes import MemoryImageGeometry
from test.files.fakes import BUCKET, StorageServer
from test.image_samples import make_image
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


def test_batched_sources_keep_historical_prices_even_when_print_is_retired(
    engine: Engine, seed: Seed
) -> None:
    prints = SqlAlchemyPrintRepository(engine, BUCKET)
    first = prints.create(seed.actor, seed.name, None, seed.file_id, 400)
    second = prints.create_version(seed.actor, first.id, 1, seed.file_id, 800)
    with Session(engine) as session, session.begin():
        parent = session.get(PrintModel, first.id)
        assert parent is not None
        parent.active = False
    selections = (
        AnalysisSelection(
            uuid4(), uuid4(), print_version_id=first.latest_version.id
        ),
        AnalysisSelection(uuid4(), uuid4(), print_version_id=second.id),
        AnalysisSelection(uuid4(), uuid4(), file_id=seed.file_id),
    )
    queries = []

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
        resolved = SqlAlchemyAnalysisSourceRepository(engine, BUCKET).resolve(
            selections
        )
        assert [row.print_surcharge_cents for row in resolved] == [400, 800, 0]
        assert all(row.file.id == seed.file_id for row in resolved)
        assert len(queries) == 2
    finally:
        event.remove(engine, "before_cursor_execute", track)


@pytest.mark.parametrize(
    "field,value",
    [
        ("state", "PENDIENTE_CARGA"),
        ("usage", "PREVIEW"),
        ("bucket", "another-bucket"),
    ],
)
def test_only_available_service_originals_can_be_analyzed(
    engine: Engine, seed: Seed, field: str, value: str
) -> None:
    with Session(engine) as session, session.begin():
        row = session.get(FileModel, seed.file_id)
        assert row is not None
        setattr(row, field, value)
    with pytest.raises(DesignAnalysisError) as error:
        SqlAlchemyAnalysisSourceRepository(engine, BUCKET).resolve(
            (AnalysisSelection(uuid4(), uuid4(), file_id=seed.file_id),)
        )
    assert error.value.failure is AnalysisFailure.ANALYSIS_SOURCE_NOT_READY


@pytest.mark.parametrize("print_source", [False, True])
def test_missing_source_is_not_fabricated(
    engine: Engine, print_source: bool
) -> None:
    selection = (
        AnalysisSelection(uuid4(), uuid4(), print_version_id=uuid4())
        if print_source
        else AnalysisSelection(uuid4(), uuid4(), file_id=uuid4())
    )
    with pytest.raises(DesignAnalysisError) as error:
        SqlAlchemyAnalysisSourceRepository(engine, BUCKET).resolve(
            (selection,)
        )
    assert error.value.failure is AnalysisFailure.ANALYSIS_SOURCE_NOT_FOUND


def test_unsafe_combined_price_is_rejected_before_image_reads(
    engine: Engine, series: Series, seed: Seed
) -> None:
    prints = SqlAlchemyPrintRepository(engine, BUCKET)
    stamp = prints.create(
        seed.actor, seed.name, None, seed.file_id, MAX_SURCHARGE_CENTS
    )
    templates = SqlAlchemyTemplateRepository(engine)
    template = templates.create(
        series.actor_id, series.product_id, 1, 0, definition()
    )
    selection = AnalysisSelection(
        template.zones[0].id,
        template.zones[0].sizes[0].id,
        print_version_id=stamp.latest_version.id,
    )
    images = MemoryImageGeometry()
    with pytest.raises(DesignAnalysisError) as error:
        DesignAnalysisService(
            templates,
            SqlAlchemyAnalysisSourceRepository(engine, BUCKET),
            images,
            None,
        ).analyze(
            VerifiedIdentity(series.actor_id, AppRole.ADMINISTRATOR),
            template.header.id,
            (selection,),
        )
    assert (
        error.value.failure is AnalysisFailure.PERSONALIZATION_AMOUNT_OVERFLOW
    )
    assert images.calls == []


def test_real_jwt_http_analysis_reads_original_once_and_writes_no_design(
    engine: Engine,
    settings: Settings,
    series: Series,
    seed: Seed,
    sign_token: Callable[..., str],
    claims: dict[str, object],
    jwks_transport: object,
) -> None:
    prints = SqlAlchemyPrintRepository(engine, BUCKET)
    stamp = prints.create(seed.actor, seed.name, None, seed.file_id, 500)
    templates = SqlAlchemyTemplateRepository(engine)
    value = definition()
    value = replace(
        value, zones=(*value.zones, replace(value.zones[0], side=Side.BACK))
    )
    template = templates.create(
        series.actor_id, series.product_id, 1, 0, value
    )
    body = {
        "applications": [
            {
                "zoneId": str(template.zones[0].id),
                "zoneSizeId": str(template.zones[0].sizes[0].id),
                "printVersionId": str(stamp.latest_version.id),
            },
            {
                "zoneId": str(template.zones[1].id),
                "zoneSizeId": str(template.zones[1].sizes[0].id),
                "fileId": str(seed.file_id),
            },
        ]
    }
    server = StorageServer()
    server.objects[f"{BUCKET}/{seed.file_id}.png"] = make_image()
    storage = server.adapter()
    app = create_app(
        settings,
        Ready(),
        template_repository=templates,
        analysis_sources=SqlAlchemyAnalysisSourceRepository(engine, BUCKET),
        image_geometry=PillowImageGeometry(storage, settings.image_policy),
        storage=storage,
    )
    payload = {
        **claims,
        "sub": str(series.actor_id),
        "app_metadata": {"app_role": "administrador"},
    }
    headers = {"Authorization": "Bearer " + sign_token(payload)}

    def counts() -> tuple[int, ...]:
        with Session(engine) as session:
            return tuple(
                session.scalar(select(func.count()).select_from(model)) or 0
                for model in (DesignModel, ApplicationModel, AuditEntryModel)
            )

    before = counts()
    try:
        with TestClient(app) as client:
            path = (
                f"/api/v1/admin/template-versions/{template.header.id}"
                "/design-analyses"
            )
            response = client.post(path, headers=headers, json=body)
            assert response.status_code == 200
            assert response.json()["personalizationSurchargeCents"] == 3000
            assert response.json()["minimumDpi"] is None
            assert (
                response.json()["diagnosticOnly"] is True
                and not response.json()["catalogCompatibilityVerified"]
            )
            assert all(
                item["resolutionStatus"] == "THRESHOLD_NOT_CONFIGURED"
                for item in response.json()["applications"]
            )
            assert (
                sum(
                    "object/authenticated/" in request.url.path
                    for request in server.requests
                )
                == 1
            )
            count = len(server.requests)
            denied = client.post(
                path,
                headers={"Authorization": "Bearer " + sign_token(claims)},
                json=body,
            )
            assert denied.status_code == 403 and len(server.requests) == count
        assert counts() == before
        assert templates.get(template.header.id).header.active is False
        assert prints.get(stamp.id).latest_version == stamp.latest_version
    finally:
        storage.close()
