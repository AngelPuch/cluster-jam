"""Model immutable versions without external service assumptions."""

from decimal import Decimal
from uuid import UUID, uuid4

from personalization.application.errors.template_error import (
    TemplateError,
    TemplateFailure,
)
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


def definition() -> TemplateDefinition:
    return TemplateDefinition(
        Dimensions(Decimal("400"), Decimal("600")),
        Dimensions(Decimal("400"), Decimal("600")),
        (
            ZoneDefinition(
                "chest",
                Side.FRONT,
                Decimal("50"),
                Decimal("50"),
                Dimensions(Decimal("200"), Decimal("300")),
                (
                    SizeDefinition(
                        SizeLabel.SMALL,
                        Dimensions(Decimal("100"), Decimal("150")),
                        1250,
                    ),
                ),
            ),
        ),
    )


def request_body(product_id: UUID | None = None) -> dict[str, object]:
    return {
        "productId": str(product_id or uuid4()),
        "sizeId": 1,
        "expectedVersion": 0,
        "front": {"widthMm": "400", "heightMm": "600"},
        "back": {"widthMm": "400", "heightMm": "600"},
        "zones": [
            {
                "code": "chest",
                "side": "FRONT",
                "xMm": "50",
                "yMm": "50",
                "widthMm": "200",
                "heightMm": "300",
                "sizes": [
                    {
                        "label": "SMALL",
                        "widthMm": "100",
                        "heightMm": "150",
                        "surchargeCents": 1250,
                    }
                ],
            }
        ],
    }


class MemoryTemplateRepository:
    def __init__(self) -> None:
        self.records: dict[UUID, TemplateRecord] = {}
        self.actors: list[UUID] = []
        self.calls = 0
        self.unavailable = False

    def _check(self) -> None:
        self.calls += 1
        if self.unavailable:
            raise TemplateError(TemplateFailure.TEMPLATE_DATABASE_UNAVAILABLE)

    def create(
        self,
        actor_id: UUID,
        product_id: UUID,
        size_id: int,
        expected_version: int,
        definition: TemplateDefinition,
    ) -> TemplateRecord:
        self._check()
        latest = max(
            (
                record.header.number
                for record in self.records.values()
                if record.header.product_id == product_id
                and record.header.size_id == size_id
            ),
            default=0,
        )
        if expected_version != latest:
            raise TemplateError(TemplateFailure.TEMPLATE_VERSION_CONFLICT)
        header = TemplateHeader(
            uuid4(),
            product_id,
            size_id,
            latest + 1,
            definition.front,
            definition.back,
            False,
        )
        zones = tuple(
            ZoneRecord(
                uuid4(),
                zone,
                tuple(SizeRecord(uuid4(), size) for size in zone.sizes),
            )
            for zone in definition.zones
        )
        result = TemplateRecord(header, zones)
        self.records[header.id] = result
        self.actors.append(actor_id)
        return result

    def get(self, template_id: UUID) -> TemplateRecord:
        self._check()
        if template_id not in self.records:
            raise TemplateError(TemplateFailure.TEMPLATE_NOT_FOUND)
        return self.records[template_id]

    def list(
        self, product_id: UUID, size_id: int, after: int | None, limit: int
    ) -> tuple[TemplateHeader, ...]:
        self._check()
        return tuple(
            sorted(
                (
                    record.header
                    for record in self.records.values()
                    if record.header.product_id == product_id
                    and record.header.size_id == size_id
                    and (after is None or record.header.number > after)
                ),
                key=lambda row: row.number,
            )[:limit]
        )
