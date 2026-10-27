"""Verify real PostgreSQL revisions, constraints, and mappings."""

import os
from collections.abc import Iterator
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from alembic import command
from sqlalchemy import Connection, Engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from personalization.infrastructure.config.settings import Settings
from personalization.infrastructure.database.engine import (
    create_database_engine,
)
from personalization.infrastructure.database.migrate import run_migrations
from personalization.infrastructure.database.migration_config import (
    CURRENT_REVISION,
    migration_config,
)
from personalization.infrastructure.database.models import (
    ApplicationModel,
    AuditEntryModel,
    Base,
    DesignModel,
    FileModel,
    PrintModel,
    PrintVersionModel,
    TemplateVersionModel,
    ZoneModel,
    ZoneSizeModel,
)
from personalization.infrastructure.database.readiness import (
    SqlAlchemyReadinessAdapter,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("PERSONALIZATION_DATABASE_INTEGRATION") != "1",
        reason="Requires the disposable Docker integration database",
    ),
]


@pytest.fixture(scope="module")
def settings() -> Settings:
    return Settings()


@pytest.fixture(scope="module")
def engine(settings: Settings) -> Iterator[Engine]:
    database = create_database_engine(settings)
    try:
        # Never reset a populated development or production schema.
        if inspect(database).get_table_names(schema="app"):
            raise RuntimeError("Integration tests require an empty app schema")
        readiness = SqlAlchemyReadinessAdapter(database, settings)
        assert readiness.is_ready() is False
        run_migrations(database, settings, "upgrade")
        assert readiness.is_ready() is True
        yield database
        with database.begin() as connection:
            configuration = migration_config()
            configuration.attributes["connection"] = connection
            command.downgrade(configuration, "base")
        assert inspect(database).get_table_names(schema="app") == [
            "alembic_version"
        ]
        assert readiness.is_ready() is False
        run_migrations(database, settings, "upgrade")
        run_migrations(database, settings, "check")
        assert readiness.is_ready() is True
    finally:
        database.dispose()


@pytest.fixture
def connection(engine: Engine) -> Iterator[Connection]:
    with engine.connect() as active_connection:
        transaction = active_connection.begin()
        try:
            yield active_connection
        finally:
            transaction.rollback()


@pytest.fixture
def session(connection: Connection) -> Iterator[Session]:
    with Session(bind=connection) as active_session:
        yield active_session


@pytest.fixture
def records(session: Session) -> dict[str, UUID]:
    owner = uuid4()
    image = FileModel(
        owner_id=owner,
        bucket="test-originals",
        object_key=str(uuid4()),
        sha256="a" * 64,
        mime_type="image/png",
        size_bytes=1024,
        width_px=400,
        height_px=400,
        usage="ORIGINAL",
        state="VALIDADO",
    )
    session.add(image)
    session.flush()
    stamp = PrintModel(name="Test print", description=None, active=True)
    session.add(stamp)
    session.flush()
    print_version = PrintVersionModel(
        print_id=stamp.id,
        number=1,
        file_id=image.id,
        surcharge_cents=125,
    )
    session.add(print_version)
    template = TemplateVersionModel(
        product_id=uuid4(),
        size_id=1,
        number=1,
        front_width_mm=Decimal("500.123456789"),
        front_height_mm=Decimal("600"),
        back_width_mm=Decimal("500"),
        back_height_mm=Decimal("600"),
        active=True,
    )
    session.add(template)
    session.flush()
    zone = ZoneModel(
        template_id=template.id,
        code="CHEST",
        side="FRENTE",
        x_mm=Decimal("10.125"),
        y_mm=Decimal("20"),
        width_mm=Decimal("200"),
        height_mm=Decimal("200"),
    )
    other_zone = ZoneModel(
        template_id=template.id,
        code="BACK",
        side="ESPALDA",
        x_mm=Decimal("10"),
        y_mm=Decimal("20"),
        width_mm=Decimal("200"),
        height_mm=Decimal("200"),
    )
    session.add_all([zone, other_zone])
    session.flush()
    size = ZoneSizeModel(
        zone_id=zone.id,
        label="chico",
        width_mm=Decimal("100.25"),
        height_mm=Decimal("100.25"),
        surcharge_cents=250,
    )
    other_size = ZoneSizeModel(
        zone_id=other_zone.id,
        label="chico",
        width_mm=Decimal("100"),
        height_mm=Decimal("100"),
        surcharge_cents=250,
    )
    design = DesignModel(
        user_id=owner,
        variant_id=uuid4(),
        template_id=template.id,
        state="BORRADOR",
        version=1,
        front_preview_id=None,
        back_preview_id=None,
    )
    session.add_all([size, other_size, design])
    session.flush()
    application = ApplicationModel(
        design_id=design.id,
        zone_id=zone.id,
        zone_size_id=size.id,
        print_version_id=print_version.id,
        user_file_id=None,
    )
    session.add(application)
    session.flush()
    return {
        "file": image.id,
        "print": stamp.id,
        "print_version": print_version.id,
        "template": template.id,
        "zone": zone.id,
        "size": size.id,
        "other_size": other_size.id,
        "design": design.id,
        "application": application.id,
    }


def test_schema_matches_current_models(
    engine: Engine,
    settings: Settings,
) -> None:
    assert set(inspect(engine).get_table_names(schema="app")) == {
        *(table.name for table in Base.metadata.sorted_tables),
        "alembic_version",
    }
    run_migrations(engine, settings, "check")
    run_migrations(engine, settings, "current")
    with engine.connect() as connection:
        assert connection.dialect.default_schema_name == "pg_catalog"
        assert (
            connection.execute(
                text("SELECT version_num FROM app.alembic_version")
            ).scalar_one()
            == CURRENT_REVISION
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM pg_tables "
                    "WHERE schemaname = 'public'"
                )
            ).scalar_one()
            == 0
        )


def test_exact_decimal_and_bigint_round_trip(
    session: Session,
    records: dict[str, UUID],
) -> None:
    session.expire_all()
    template = session.get(TemplateVersionModel, records["template"])
    assert template is not None
    assert template.front_width_mm == Decimal("500.123456789")
    assert isinstance(template.front_width_mm, Decimal)
    version = session.get(PrintVersionModel, records["print_version"])
    assert version is not None
    version.surcharge_cents = 9_007_199_254_740_991
    session.flush()
    session.expire_all()
    assert version.surcharge_cents == 9_007_199_254_740_991


@pytest.mark.parametrize(
    ("sql", "key", "state"),
    [
        ("UPDATE app.archivo SET bytes = 0 WHERE id = :id", "file", "23514"),
        (
            "UPDATE app.archivo SET ancho_px = -1 WHERE id = :id",
            "file",
            "23514",
        ),
        (
            "UPDATE app.archivo SET sha256 = 'invalid' WHERE id = :id",
            "file",
            "23514",
        ),
        (
            "UPDATE app.archivo SET mime = 'text/plain' WHERE id = :id",
            "file",
            "23514",
        ),
        (
            (
                "UPDATE app.estampado_version SET "
                "recargo_centavos = -1 WHERE id = :id"
            ),
            "print_version",
            "23514",
        ),
        (
            "UPDATE app.estampado_version SET numero = 0 WHERE id = :id",
            "print_version",
            "23514",
        ),
        (
            (
                "UPDATE app.plantilla_version SET alto_frente_mm "
                "= 0 WHERE id = :id"
            ),
            "template",
            "23514",
        ),
        ("UPDATE app.zona SET x_mm = -1 WHERE id = :id", "zone", "23514"),
        ("UPDATE app.zona SET cara = 'LEFT' WHERE id = :id", "zone", "23514"),
        (
            "UPDATE app.zona SET ancho_mm = 'NaN'::numeric WHERE id = :id",
            "zone",
            "23514",
        ),
        (
            (
                "UPDATE app.zona SET ancho_mm = "
                "'Infinity'::numeric WHERE id = :id"
            ),
            "zone",
            "23514",
        ),
        (
            "UPDATE app.tamano_zona SET recargo_centavos = -1 WHERE id = :id",
            "size",
            "23514",
        ),
        (
            "UPDATE app.diseno SET version = 0 WHERE id = :id",
            "design",
            "23514",
        ),
        (
            (
                "UPDATE app.aplicacion SET estampado_version_id ="
                " NULL WHERE id = :id"
            ),
            "application",
            "23514",
        ),
        ("DELETE FROM app.archivo WHERE id = :id", "file", "23503"),
    ],
)
def test_invalid_rows_are_rejected_by_postgresql(
    connection: Connection,
    records: dict[str, UUID],
    sql: str,
    key: str,
    state: str,
) -> None:
    with pytest.raises(IntegrityError) as caught:
        connection.execute(text(sql), {"id": records[key]})
    assert getattr(caught.value.orig, "sqlstate", None) == state


def test_application_requires_exactly_one_source(
    connection: Connection,
    records: dict[str, UUID],
) -> None:
    with pytest.raises(IntegrityError) as caught:
        connection.execute(
            text(
                "UPDATE app.aplicacion SET archivo_usuario_id = :file "
                "WHERE id = :id"
            ),
            {"file": records["file"], "id": records["application"]},
        )
    assert getattr(caught.value.orig, "sqlstate", None) == "23514"


def test_composite_foreign_key_rejects_size_from_another_zone(
    connection: Connection,
    records: dict[str, UUID],
) -> None:
    with pytest.raises(IntegrityError) as caught:
        connection.execute(
            text("UPDATE app.aplicacion SET tamano_id = :size WHERE id = :id"),
            {"size": records["other_size"], "id": records["application"]},
        )
    assert getattr(caught.value.orig, "sqlstate", None) == "23503"


def test_private_file_is_a_valid_alternative_source(
    connection: Connection,
    records: dict[str, UUID],
) -> None:
    connection.execute(
        text(
            "UPDATE app.aplicacion SET estampado_version_id = NULL, "
            "archivo_usuario_id = :file WHERE id = :id"
        ),
        {"file": records["file"], "id": records["application"]},
    )


@pytest.mark.parametrize(
    "resource",
    [
        "archivo",
        "estampado_version",
        "plantilla_version",
        "zona",
        "tamano_zona",
        "aplicacion",
    ],
)
def test_documented_unique_keys_reject_duplicate_rows(
    connection: Connection,
    records: dict[str, UUID],
    resource: str,
) -> None:
    table = Base.metadata.tables["app." + resource]
    columns = [column.name for column in table.columns if column.name != "id"]
    names = ", ".join(columns)
    with pytest.raises(IntegrityError) as caught:
        connection.execute(
            text(
                f"INSERT INTO app.{resource} (id, {names}) "
                f"SELECT :id, {names} FROM app.{resource} LIMIT 1"
            ),
            {"id": uuid4()},
        )
    assert getattr(caught.value.orig, "sqlstate", None) == "23505"


def test_audit_jsonb_and_timestamp_are_local(
    session: Session,
) -> None:
    entry = AuditEntryModel(
        actor_id=None,
        action="CREATE_TEMPLATE",
        resource="plantilla_version",
        resource_id=uuid4(),
        detail={"version": 1},
    )
    session.add(entry)
    session.flush()
    session.expire_all()
    assert entry.detail == {"version": 1}
    assert entry.created_at.tzinfo is not None


def test_upgrade_at_head_preserves_existing_rows(
    engine: Engine,
    settings: Settings,
) -> None:
    image_id = uuid4()
    with Session(engine) as session:
        session.add(
            FileModel(
                id=image_id,
                owner_id=uuid4(),
                bucket="persistent-test",
                object_key=str(uuid4()),
                sha256="b" * 64,
                mime_type="image/jpeg",
                size_bytes=10,
                width_px=1,
                height_px=1,
                usage="ORIGINAL",
                state="VALIDADO",
            )
        )
        session.commit()
    try:
        run_migrations(engine, settings, "upgrade")
        with engine.connect() as connection:
            assert (
                connection.execute(
                    select(FileModel.id).where(FileModel.id == image_id)
                ).scalar_one()
                == image_id
            )
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM app.archivo WHERE id = :id"),
                {"id": image_id},
            )


def test_readiness_rejects_an_outdated_revision(
    engine: Engine,
    settings: Settings,
) -> None:
    try:
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE app.alembic_version SET version_num = 'outdated'")
            )
        assert SqlAlchemyReadinessAdapter(engine, settings).is_ready() is False
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE app.alembic_version SET version_num = :revision"),
                {"revision": CURRENT_REVISION},
            )
