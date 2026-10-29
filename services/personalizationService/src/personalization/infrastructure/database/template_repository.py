"""Commit draft geometry, versions, and audit atomically."""

from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from personalization.application.errors.template_error import (
    TemplateError,
    TemplateFailure,
)
from personalization.application.prints.print_record import MAX_VERSION_NUMBER
from personalization.application.templates.template_record import (
    Dimensions,
    Side,
    SizeDefinition,
    SizeLabel,
    SizeRecord,
    TemplateDefinition,
    TemplateHeader,
    TemplateRecord,
    ZoneDefinition,
    ZoneRecord,
)
from personalization.infrastructure.database.models.audit_entry import (
    AuditEntryModel,
)
from personalization.infrastructure.database.models.template_version import (
    TemplateVersionModel,
)
from personalization.infrastructure.database.models.zone import ZoneModel
from personalization.infrastructure.database.models.zone_size import (
    ZoneSizeModel,
)

SIDE_SQL = {Side.FRONT: "FRENTE", Side.BACK: "ESPALDA"}
LABEL_SQL = {
    SizeLabel.SMALL: "CHICO",
    SizeLabel.MEDIUM: "MEDIANO",
    SizeLabel.LARGE: "GRANDE",
}


def map_header(row: TemplateVersionModel) -> TemplateHeader:
    return TemplateHeader(
        row.id,
        row.product_id,
        row.size_id,
        row.number,
        Dimensions(row.front_width_mm, row.front_height_mm),
        Dimensions(row.back_width_mm, row.back_height_mm),
        row.active,
    )


class SqlAlchemyTemplateRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create(
        self,
        actor_id: UUID,
        product_id: UUID,
        size_id: int,
        expected_version: int,
        definition: TemplateDefinition,
    ) -> TemplateRecord:
        key = int.from_bytes(
            sha256(
                b"template-series:"
                + product_id.bytes
                + size_id.to_bytes(2, "big")
            ).digest()[:8],
            signed=True,
        )
        try:
            with Session(self._engine) as session, session.begin():
                session.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"), {"key": key}
                )
                latest = (
                    session.scalar(
                        select(func.max(TemplateVersionModel.number)).where(
                            TemplateVersionModel.product_id == product_id,
                            TemplateVersionModel.size_id == size_id,
                        )
                    )
                    or 0
                )
                if latest != expected_version:
                    raise TemplateError(
                        TemplateFailure.TEMPLATE_VERSION_CONFLICT
                    )
                if latest == MAX_VERSION_NUMBER:
                    raise TemplateError(TemplateFailure.TEMPLATE_VERSION_LIMIT)
                row = TemplateVersionModel(
                    id=uuid4(),
                    product_id=product_id,
                    size_id=size_id,
                    number=latest + 1,
                    front_width_mm=definition.front.width_mm,
                    front_height_mm=definition.front.height_mm,
                    back_width_mm=definition.back.width_mm,
                    back_height_mm=definition.back.height_mm,
                    active=False,
                )
                session.add(row)
                session.flush()
                zones: list[ZoneRecord] = []
                for zone in definition.zones:
                    zone_row = ZoneModel(
                        id=uuid4(),
                        template_id=row.id,
                        code=zone.code,
                        side=SIDE_SQL[zone.side],
                        x_mm=zone.x_mm,
                        y_mm=zone.y_mm,
                        width_mm=zone.dimensions.width_mm,
                        height_mm=zone.dimensions.height_mm,
                    )
                    session.add(zone_row)
                    session.flush()
                    sizes: list[SizeRecord] = []
                    for size in zone.sizes:
                        size_row = ZoneSizeModel(
                            id=uuid4(),
                            zone_id=zone_row.id,
                            label=LABEL_SQL[size.label],
                            width_mm=size.dimensions.width_mm,
                            height_mm=size.dimensions.height_mm,
                            surcharge_cents=size.surcharge_cents,
                        )
                        session.add(size_row)
                        sizes.append(SizeRecord(size_row.id, size))
                    zones.append(ZoneRecord(zone_row.id, zone, tuple(sizes)))
                session.flush()
                session.add(
                    AuditEntryModel(
                        id=uuid4(),
                        actor_id=actor_id,
                        action="TEMPLATE_VERSION_CREATED",
                        resource="plantilla_version",
                        resource_id=row.id,
                        detail={
                            "productId": str(product_id),
                            "sizeId": size_id,
                            "versionNumber": row.number,
                            "zoneCount": len(zones),
                            "sizeCount": sum(
                                len(zone.sizes) for zone in zones
                            ),
                            "active": False,
                            "catalogValidation": "PENDING",
                        },
                    )
                )
                session.flush()
                result = TemplateRecord(map_header(row), tuple(zones))
            return result
        except SQLAlchemyError:
            raise TemplateError(
                TemplateFailure.TEMPLATE_DATABASE_UNAVAILABLE
            ) from None

    def get(self, template_id: UUID) -> TemplateRecord:
        statement = (
            select(TemplateVersionModel, ZoneModel, ZoneSizeModel)
            .outerjoin(
                ZoneModel, ZoneModel.template_id == TemplateVersionModel.id
            )
            .outerjoin(ZoneSizeModel, ZoneSizeModel.zone_id == ZoneModel.id)
            .where(TemplateVersionModel.id == template_id)
            .order_by(ZoneModel.side, ZoneModel.code, ZoneSizeModel.label)
        )
        try:
            with Session(self._engine) as session:
                rows = session.execute(statement).all()
                if not rows:
                    raise TemplateError(TemplateFailure.TEMPLATE_NOT_FOUND)
                grouped: dict[UUID, tuple[ZoneModel, list[SizeRecord]]] = {}
                for _, zone, size in rows:
                    if zone is None or size is None:
                        raise TemplateError(
                            TemplateFailure.TEMPLATE_DATABASE_UNAVAILABLE
                        )
                    label = next(
                        label
                        for label, value in LABEL_SQL.items()
                        if value == size.label
                    )
                    grouped.setdefault(zone.id, (zone, []))[1].append(
                        SizeRecord(
                            size.id,
                            SizeDefinition(
                                label,
                                Dimensions(size.width_mm, size.height_mm),
                                size.surcharge_cents,
                            ),
                        )
                    )
                zones: list[ZoneRecord] = []
                for zone, sizes in grouped.values():
                    side = next(
                        side
                        for side, value in SIDE_SQL.items()
                        if value == zone.side
                    )
                    definition = ZoneDefinition(
                        zone.code,
                        side,
                        zone.x_mm,
                        zone.y_mm,
                        Dimensions(zone.width_mm, zone.height_mm),
                        tuple(size.definition for size in sizes),
                    )
                    zones.append(ZoneRecord(zone.id, definition, tuple(sizes)))
                return TemplateRecord(map_header(rows[0][0]), tuple(zones))
        except SQLAlchemyError, ValueError, StopIteration:
            raise TemplateError(
                TemplateFailure.TEMPLATE_DATABASE_UNAVAILABLE
            ) from None

    def list(
        self,
        product_id: UUID,
        size_id: int,
        after: int | None,
        limit: int,
    ) -> tuple[TemplateHeader, ...]:
        statement = (
            select(TemplateVersionModel)
            .where(
                TemplateVersionModel.product_id == product_id,
                TemplateVersionModel.size_id == size_id,
            )
            .order_by(TemplateVersionModel.number)
            .limit(max(1, min(limit, 101)))
        )
        if after is not None:
            statement = statement.where(TemplateVersionModel.number > after)
        try:
            with Session(self._engine) as session:
                return tuple(
                    map_header(row) for row in session.scalars(statement)
                )
        except SQLAlchemyError:
            raise TemplateError(
                TemplateFailure.TEMPLATE_DATABASE_UNAVAILABLE
            ) from None
