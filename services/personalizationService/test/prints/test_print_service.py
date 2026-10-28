"""Exercise admin rules, exact money and scoped pagination."""

from uuid import UUID, uuid4

import pytest

from personalization.application.errors.print_error import (
    PrintError,
    PrintFailure,
)
from personalization.application.errors.security_error import SecurityError
from personalization.application.prints.cursor import (
    encode_cursor,
    print_cursor,
    version_cursor,
)
from personalization.application.prints.print_record import MAX_SURCHARGE_CENTS
from personalization.application.prints.print_service import PrintService
from personalization.application.security.identity import (
    AppRole,
    VerifiedIdentity,
)
from test.prints.fakes import MemoryPrintRepository

ADMIN = VerifiedIdentity(UUID(int=900), AppRole.ADMINISTRATOR)
CLIENT = VerifiedIdentity(UUID(int=901), AppRole.CLIENT)


@pytest.mark.parametrize(
    "operation",
    [
        "create",
        "create_version",
        "get",
        "get_version",
        "list",
        "versions",
    ],
)
def test_every_use_case_authorizes_before_repository(operation: str) -> None:
    repository = MemoryPrintRepository()
    service = PrintService(repository)
    with pytest.raises(SecurityError):
        match operation:
            case "create":
                service.create(CLIENT, "Print", None, uuid4(), 50)
            case "create_version":
                service.create_version(CLIENT, uuid4(), 1, uuid4(), 50)
            case "get":
                service.get(CLIENT, uuid4())
            case "get_version":
                service.get_version(CLIENT, uuid4(), uuid4())
            case "list":
                service.list(CLIENT)
            case _:
                service.list_versions(CLIENT, uuid4())
    assert repository.calls == 0


@pytest.mark.parametrize("surcharge", [-1, True, MAX_SURCHARGE_CENTS + 1])
def test_money_must_be_nonnegative_exact_and_json_safe(surcharge: int) -> None:
    repository = MemoryPrintRepository()
    service = PrintService(repository)
    with pytest.raises(PrintError):
        service.create(ADMIN, "Print", None, uuid4(), surcharge)
    with pytest.raises(PrintError):
        service.create_version(ADMIN, uuid4(), 1, uuid4(), surcharge)
    assert repository.calls == 0


@pytest.mark.parametrize(
    "name,description",
    [
        ("   ", None),
        ("x" * 121, None),
        ("Valid", "x" * 2001),
    ],
)
def test_invalid_metadata_never_writes(
    name: str, description: str | None
) -> None:
    repository = MemoryPrintRepository()
    with pytest.raises(PrintError):
        PrintService(repository).create(ADMIN, name, description, uuid4(), 0)
    assert repository.calls == 0


@pytest.mark.parametrize("expected", [0, -1, True, 2_147_483_648])
def test_invalid_expected_version_never_writes(expected: int) -> None:
    repository = MemoryPrintRepository()
    with pytest.raises(PrintError):
        PrintService(repository).create_version(
            ADMIN, uuid4(), expected, uuid4(), 0
        )
    assert repository.calls == 0


def test_versions_remain_addressable_and_stale_retry_conflicts() -> None:
    repository = MemoryPrintRepository()
    service = PrintService(repository)
    created = service.create(ADMIN, "  Logo  ", "Description", uuid4(), 0)
    second = service.create_version(ADMIN, created.id, 1, uuid4(), 1250)
    assert service.get(ADMIN, created.id).latest_version == second
    assert (
        service.get_version(
            ADMIN, created.id, created.latest_version.id
        ).surcharge_cents
        == 0
    )
    assert created.name == "Logo"
    assert repository.actors == [ADMIN.user_id, ADMIN.user_id]
    with pytest.raises(PrintError) as caught:
        service.create_version(ADMIN, created.id, 1, uuid4(), 1500)
    assert caught.value.failure is PrintFailure.PRINT_VERSION_CONFLICT
    assert len(repository.versions[created.id]) == 2


def test_pagination_has_stable_order_and_no_duplicates() -> None:
    service = PrintService(MemoryPrintRepository())
    created = [
        service.create(ADMIN, str(i), None, uuid4(), i) for i in range(3)
    ]
    first = service.list(ADMIN, limit=2)
    second = service.list(ADMIN, limit=2, cursor=first.next_cursor)
    assert first.items + second.items == tuple(created)
    assert second.next_cursor is None
    for expected in range(1, 4):
        service.create_version(
            ADMIN, created[0].id, expected, uuid4(), expected
        )
    page = service.list_versions(ADMIN, created[0].id, 2)
    last = service.list_versions(ADMIN, created[0].id, 2, page.next_cursor)
    assert [row.number for row in page.items + last.items] == [1, 2, 3, 4]
    assert last.next_cursor is None
    with pytest.raises(PrintError):
        service.list_versions(ADMIN, created[1].id, 2, page.next_cursor)


@pytest.mark.parametrize("limit", [0, 101, True])
def test_limits_are_bounded_in_application(limit: int) -> None:
    service = PrintService(MemoryPrintRepository())
    with pytest.raises(PrintError):
        service.list(ADMIN, limit)
    with pytest.raises(PrintError):
        service.list_versions(ADMIN, uuid4(), limit)


@pytest.mark.parametrize(
    "cursor",
    [
        "",
        "*",
        "x" * 257,
        "!!!!",
        "cHJpbnRzOjE",
        "====",
        encode_cursor("wrong", uuid4()),
        encode_cursor("prints", "bad-uuid"),
        encode_cursor("prints", str(uuid4()).upper()),
    ],
)
def test_invalid_print_cursors_are_rejected(cursor: str) -> None:
    with pytest.raises(PrintError) as caught:
        print_cursor(cursor)
    assert caught.value.failure is PrintFailure.INVALID_CURSOR


@pytest.mark.parametrize("value", ["0", "-1", "01", "a", "2147483648"])
def test_invalid_version_cursors_are_rejected(value: str) -> None:
    print_id = uuid4()
    with pytest.raises(PrintError):
        version_cursor(
            encode_cursor(f"print-versions/{print_id}", value), print_id
        )


def test_empty_pages_and_cursor_round_trip() -> None:
    service = PrintService(MemoryPrintRepository())
    assert service.list(ADMIN).items == ()
    assert service.list(ADMIN).next_cursor is None
    key = uuid4()
    assert print_cursor(encode_cursor("prints", key)) == key
    assert version_cursor(None, key) is None
