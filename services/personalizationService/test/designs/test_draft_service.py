"""Verify owner isolation, immutable copies and draft revisions."""

from dataclasses import replace
from uuid import uuid4

import pytest

from personalization.application.designs.draft_record import (
    DesignCondition,
    DesignState,
    DraftContent,
    draft_revision,
)
from personalization.application.designs.draft_service import DraftService
from personalization.application.errors.design_error import (
    DesignError,
    DesignFailure,
)
from personalization.application.errors.security_error import SecurityError
from personalization.application.prints.cursor import encode_cursor
from personalization.application.security.identity import (
    AppRole,
    VerifiedIdentity,
)
from test.designs.draft_fakes import MemoryDesignRepository
from test.designs.fakes import analysis_data

ADMIN = VerifiedIdentity(uuid4(), AppRole.ADMINISTRATOR)
OTHER = VerifiedIdentity(uuid4(), AppRole.ADMINISTRATOR)


def test_save_edit_noop_and_copy_preserve_source_and_owner() -> None:
    data = analysis_data()
    repository = MemoryDesignRepository()
    service = DraftService(repository, data.templates)
    content = DraftContent(uuid4(), data.template.header.id, data.selections)
    created = service.create(ADMIN, content)
    assert (
        created.owner_id == ADMIN.user_id
        and created.state is DesignState.DRAFT
    )
    same = service.update(
        ADMIN,
        created.id,
        replace(content, applications=tuple(reversed(content.applications))),
        DesignCondition(frozenset({draft_revision(created)})),
    )
    assert same == created and len(repository.audit) == 1
    empty = service.update(
        ADMIN,
        created.id,
        replace(content, applications=()),
        DesignCondition(frozenset({draft_revision(created)})),
    )
    assert empty.version == 2 and empty.applications == ()
    with pytest.raises(DesignError) as stale:
        service.update(
            ADMIN,
            created.id,
            content,
            DesignCondition(frozenset({draft_revision(created)})),
        )
    assert stale.value.failure is DesignFailure.DESIGN_PRECONDITION_FAILED
    copy = service.copy(ADMIN, created.id)
    assert (
        copy.id != empty.id
        and copy.version == 1
        and copy.state is DesignState.DRAFT
    )
    assert repository.get(ADMIN.user_id, empty.id) == empty


@pytest.mark.parametrize("operation", ["get", "update", "copy"])
def test_another_administrator_cannot_access_saved_draft(
    operation: str,
) -> None:
    data = analysis_data()
    repository = MemoryDesignRepository()
    service = DraftService(repository, data.templates)
    content = DraftContent(uuid4(), data.template.header.id, data.selections)
    created = service.create(ADMIN, content)
    with pytest.raises(SecurityError):
        if operation == "get":
            service.get(OTHER, created.id)
        elif operation == "copy":
            service.copy(OTHER, created.id)
        else:
            service.update(
                OTHER, created.id, content, DesignCondition(any_existing=True)
            )
    assert service.list(OTHER).items == () and len(repository.audit) == 1


@pytest.mark.parametrize(
    "operation", ["create", "get", "update", "copy", "list"]
)
def test_customer_role_cannot_use_administrative_drafts(
    operation: str,
) -> None:
    data = analysis_data()
    repository = MemoryDesignRepository()
    service = DraftService(repository, data.templates)
    customer = VerifiedIdentity(uuid4(), AppRole.CLIENT)
    content = DraftContent(uuid4(), data.template.header.id, ())
    with pytest.raises(SecurityError):
        match operation:
            case "create":
                service.create(customer, content)
            case "get":
                service.get(customer, uuid4())
            case "update":
                service.update(
                    customer,
                    uuid4(),
                    content,
                    DesignCondition(any_existing=True),
                )
            case "copy":
                service.copy(customer, uuid4())
            case _:
                service.list(customer)
    assert repository.calls == 0


def test_frozen_source_never_changes_and_copy_has_new_application_ids() -> (
    None
):
    data = analysis_data()
    repository = MemoryDesignRepository()
    service = DraftService(repository, data.templates)
    original = service.create(
        ADMIN, DraftContent(uuid4(), data.template.header.id, data.selections)
    )
    frozen = replace(original, state=DesignState.FROZEN)
    repository.records[original.id] = frozen
    with pytest.raises(DesignError) as error:
        service.update(
            ADMIN,
            frozen.id,
            frozen.content,
            DesignCondition(any_existing=True),
        )
    assert error.value.failure is DesignFailure.DESIGN_NOT_EDITABLE
    copy = service.copy(ADMIN, frozen.id)
    assert copy.id != frozen.id and copy.content == frozen.content
    assert {row.id for row in copy.applications}.isdisjoint(
        row.id for row in frozen.applications
    )
    assert repository.get(ADMIN.user_id, frozen.id) == frozen


def test_cursor_is_scoped_and_noop_revision_is_stable() -> None:
    data = analysis_data()
    repository = MemoryDesignRepository()
    service = DraftService(repository, data.templates)
    for _ in range(2):
        service.create(
            ADMIN, DraftContent(uuid4(), data.template.header.id, ())
        )
    page = service.list(ADMIN, 1)
    assert len(page.items) == 1 and page.next_cursor
    second = service.list(ADMIN, 1, page.next_cursor)
    assert len(second.items) == 1 and second.next_cursor is None
    with pytest.raises(DesignError) as error:
        service.list(OTHER, 1, page.next_cursor)
    assert error.value.failure is DesignFailure.INVALID_CURSOR
    with pytest.raises(DesignError):
        service.list(ADMIN, 1, encode_cursor("prints", uuid4()))
