"""Check partial edit semantics and strong HTTP preconditions."""

from uuid import uuid4

import pytest

from personalization.application.errors.print_error import (
    PrintError,
    PrintFailure,
)
from personalization.application.errors.security_error import SecurityError
from personalization.application.prints.print_changes import (
    PrintChanges,
    PrintCondition,
    print_revision,
)
from personalization.application.prints.print_service import PrintService
from personalization.interfaces.http.prints.preconditions import (
    parse_if_match,
    print_etag,
)
from test.prints.fakes import MemoryPrintRepository
from test.prints.test_print_service import ADMIN, CLIENT


def test_partial_edits_clear_description_and_preserve_history() -> None:
    repository = MemoryPrintRepository()
    service = PrintService(repository)
    initial = service.create(ADMIN, "Logo", "Original", uuid4(), 1250)
    condition = parse_if_match([print_etag(initial)])
    renamed = service.update(
        ADMIN,
        initial.id,
        PrintChanges(frozenset({"name"}), name=" New "),
        condition,
    )
    assert renamed.name == "New" and renamed.description == "Original"
    assert print_revision(renamed) != print_revision(initial)
    cleared = service.update(
        ADMIN,
        initial.id,
        PrintChanges(frozenset({"description"})),
        parse_if_match([print_etag(renamed)]),
    )
    assert cleared.description is None
    retired = service.update(
        ADMIN,
        initial.id,
        PrintChanges(frozenset({"active"}), active=False),
        parse_if_match([print_etag(cleared)]),
    )
    assert retired.active is False
    calls = len(repository.actors)
    unchanged = service.update(
        ADMIN,
        initial.id,
        PrintChanges(frozenset({"active"}), active=False),
        parse_if_match([print_etag(retired)]),
    )
    assert unchanged == retired and len(repository.actors) == calls
    activated = service.update(
        ADMIN,
        initial.id,
        PrintChanges(frozenset({"active"}), active=True),
        parse_if_match([print_etag(retired)]),
    )
    assert activated.active is True
    assert activated.latest_version == initial.latest_version
    assert repository.versions[initial.id] == [initial.latest_version]


def test_client_cannot_update_even_with_an_invalid_patch() -> None:
    repository = MemoryPrintRepository()
    with pytest.raises(SecurityError):
        PrintService(repository).update(
            CLIENT, uuid4(), PrintChanges(frozenset()), PrintCondition()
        )
    assert repository.calls == 0


@pytest.mark.parametrize(
    "changes",
    [
        PrintChanges(frozenset()),
        PrintChanges(frozenset({"actorId"})),
        PrintChanges(frozenset({"name"})),
        PrintChanges(frozenset({"name"}), name="  "),
        PrintChanges(frozenset({"name"}), name="x" * 121),
        PrintChanges(frozenset({"description"}), description="x" * 2001),
        PrintChanges(frozenset({"active"})),
    ],
)
def test_invalid_changes_do_not_reach_repository(
    changes: PrintChanges,
) -> None:
    repository = MemoryPrintRepository()
    with pytest.raises(PrintError) as caught:
        PrintService(repository).update(
            ADMIN, uuid4(), changes, PrintCondition(any_existing=True)
        )
    assert caught.value.failure is PrintFailure.INVALID_PRINT_DATA
    assert repository.calls == 0


def test_stale_revision_after_metadata_or_image_version_is_rejected() -> None:
    repository = MemoryPrintRepository()
    service = PrintService(repository)
    initial = service.create(ADMIN, "Logo", None, uuid4(), 0)
    original_condition = parse_if_match([print_etag(initial)])
    service.create_version(ADMIN, initial.id, 1, uuid4(), 500)
    with pytest.raises(PrintError) as caught:
        service.update(
            ADMIN,
            initial.id,
            PrintChanges(frozenset({"active"}), active=False),
            original_condition,
        )
    assert caught.value.failure is PrintFailure.PRINT_PRECONDITION_FAILED
    assert service.get(ADMIN, initial.id).active is True


@pytest.mark.parametrize(
    "values",
    [
        [],
        [""],
        [","],
        ["not-quoted"],
        ['"unterminated'],
        ['"a" "b"'],
        ['"a"garbage'],
        ['*, "a"'],
        ['w/"a"'],
        ['"line\nbreak"'],
        ['"\u2603"'],
        ['"' + "x" * 2048 + '"'],
        [", ".join('"a"' for _ in range(33))],
    ],
)
def test_malformed_or_unbounded_conditions_fail_safely(
    values: list[str],
) -> None:
    with pytest.raises(PrintError) as caught:
        parse_if_match(values)
    assert caught.value.failure is PrintFailure.INVALID_PRINT_PRECONDITION


def test_missing_condition_has_a_distinct_failure() -> None:
    with pytest.raises(PrintError) as caught:
        parse_if_match(None)
    assert caught.value.failure is PrintFailure.PRINT_PRECONDITION_REQUIRED


def test_http_lists_ignore_weak_tags_and_preserve_opaque_commas() -> None:
    condition = parse_if_match(['W/"weak", "tag,comma"', '"second",,'])
    assert condition.matches("tag,comma") and condition.matches("second")
    assert not condition.matches("weak")
    assert not parse_if_match(['W/"current"']).matches("current")
    assert parse_if_match([" * "]).any_existing
    assert parse_if_match([',"",,']).revisions == frozenset({""})


def test_etag_is_stable_for_identical_representations() -> None:
    service = PrintService(MemoryPrintRepository())
    record = service.create(ADMIN, "Logo", None, uuid4(), 0)
    assert print_etag(record) == print_etag(service.get(ADMIN, record.id))
    assert print_etag(record).startswith('"')
    assert len(print_etag(record)) == 66
