"""Verify draft version rules before touching persistence."""

from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest

from personalization.application.errors.security_error import SecurityError
from personalization.application.errors.template_error import (
    TemplateError,
    TemplateFailure,
)
from personalization.application.prints.cursor import encode_cursor
from personalization.application.prints.print_record import MAX_SURCHARGE_CENTS
from personalization.application.security.identity import (
    AppRole,
    VerifiedIdentity,
)
from personalization.application.templates.template_record import (
    Dimensions,
    Side,
)
from personalization.application.templates.template_rules import (
    validate_definition,
)
from personalization.application.templates.template_service import (
    TemplateService,
)
from test.templates.fakes import MemoryTemplateRepository, definition

ADMIN = VerifiedIdentity(uuid4(), AppRole.ADMINISTRATOR)
CLIENT = VerifiedIdentity(uuid4(), AppRole.CLIENT)


@pytest.mark.parametrize("operation", ["create", "get", "list"])
def test_role_is_checked_before_business_rules(operation: str) -> None:
    repository = MemoryTemplateRepository()
    service = TemplateService(repository)
    with pytest.raises(SecurityError):
        if operation == "create":
            service.create(CLIENT, uuid4(), 1, 0, definition())
        elif operation == "get":
            service.get(CLIENT, uuid4())
        else:
            service.list(CLIENT, uuid4(), 1)
    assert repository.calls == 0


def test_versions_are_drafts_and_preserve_previous_ids_and_sizes() -> None:
    repository = MemoryTemplateRepository()
    service = TemplateService(repository)
    product_id = uuid4()
    first = service.create(ADMIN, product_id, 1, 0, definition())
    second = service.create(ADMIN, product_id, 1, 1, definition())
    assert not first.header.active and not second.header.active
    assert first.header.number == 1 and second.header.number == 2
    assert first.zones[0].id != second.zones[0].id
    assert first.zones[0].sizes[0].id != second.zones[0].sizes[0].id
    assert service.get(ADMIN, first.header.id) == first
    page = service.list(ADMIN, product_id, 1, limit=1)
    assert page.items == (first.header,) and page.next_cursor
    next_page = service.list(
        ADMIN, product_id, 1, limit=1, cursor=page.next_cursor
    )
    assert (
        next_page.items == (second.header,) and next_page.next_cursor is None
    )
    assert repository.actors == [ADMIN.user_id, ADMIN.user_id]
    with pytest.raises(TemplateError) as stale:
        service.create(ADMIN, product_id, 1, 0, definition())
    assert stale.value.failure is TemplateFailure.TEMPLATE_VERSION_CONFLICT


def test_touching_edges_and_different_sides_are_valid() -> None:
    value = definition()
    first = value.zones[0]
    second = replace(
        first,
        code="right",
        x_mm=Decimal("250"),
        dimensions=Dimensions(Decimal("150"), Decimal("300")),
    )
    validate_definition(
        replace(value, zones=(first, second, replace(first, side=Side.BACK)))
    )


@pytest.mark.parametrize(
    "value",
    [
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-1"),
        Decimal("0"),
        Decimal("10001"),
        Decimal("0.0001"),
    ],
)
def test_dimensions_are_finite_positive_bounded_and_exact(
    value: Decimal,
) -> None:
    original = definition()
    with pytest.raises(TemplateError):
        validate_definition(
            replace(original, front=Dimensions(value, Decimal("600")))
        )


@pytest.mark.parametrize(
    "damage,expected",
    [
        ("outside", TemplateFailure.ZONE_OUTSIDE_TEMPLATE),
        ("overlap", TemplateFailure.ZONES_OVERLAP),
        ("zone-code", TemplateFailure.DUPLICATE_ZONE),
        ("size-label", TemplateFailure.DUPLICATE_ZONE_SIZE),
        ("size-outside", TemplateFailure.SIZE_OUTSIDE_ZONE),
        ("negative-money", TemplateFailure.INVALID_TEMPLATE_DATA),
        ("unsafe-money", TemplateFailure.INVALID_TEMPLATE_DATA),
        ("empty", TemplateFailure.INVALID_TEMPLATE_DATA),
    ],
)
def test_invalid_geometry_never_reaches_repository(
    damage: str, expected: TemplateFailure
) -> None:
    value = definition()
    zone = value.zones[0]
    size = zone.sizes[0]
    match damage:
        case "outside":
            value = replace(value, zones=(replace(zone, x_mm=Decimal("201")),))
        case "overlap":
            value = replace(value, zones=(zone, replace(zone, code="other")))
        case "zone-code":
            value = replace(value, zones=(zone, zone))
        case "size-label":
            value = replace(value, zones=(replace(zone, sizes=(size, size)),))
        case "size-outside":
            value = replace(
                value,
                zones=(
                    replace(
                        zone,
                        sizes=(
                            replace(
                                size,
                                dimensions=Dimensions(
                                    Decimal("201"), Decimal("150")
                                ),
                            ),
                        ),
                    ),
                ),
            )
        case "negative-money":
            value = replace(
                value,
                zones=(
                    replace(zone, sizes=(replace(size, surcharge_cents=-1),)),
                ),
            )
        case "unsafe-money":
            value = replace(
                value,
                zones=(
                    replace(
                        zone,
                        sizes=(
                            replace(
                                size, surcharge_cents=MAX_SURCHARGE_CENTS + 1
                            ),
                        ),
                    ),
                ),
            )
        case "empty":
            value = replace(value, zones=())
    repository = MemoryTemplateRepository()
    with pytest.raises(TemplateError) as error:
        TemplateService(repository).create(ADMIN, uuid4(), 1, 0, value)
    assert error.value.failure is expected and repository.calls == 0


@pytest.mark.parametrize(
    "cursor",
    [
        "invalid",
        encode_cursor("prints", uuid4()),
        encode_cursor("template-versions/other/1", 1),
    ],
)
def test_cursors_are_bound_to_product_and_size(cursor: str) -> None:
    repository = MemoryTemplateRepository()
    with pytest.raises(TemplateError) as error:
        TemplateService(repository).list(ADMIN, uuid4(), 1, cursor=cursor)
    assert error.value.failure is TemplateFailure.INVALID_CURSOR
    assert repository.calls == 0
