"""Check bounded pagination and version-specific private downloads."""

from uuid import UUID, uuid4

import pytest

from personalization.application.catalog.catalog_service import CatalogService
from personalization.application.errors.print_error import (
    PrintError,
    PrintFailure,
)
from personalization.application.prints.cursor import encode_cursor
from personalization.application.security.identity import (
    AppRole,
    VerifiedIdentity,
)
from test.catalog.fakes import MemoryCatalogRepository, catalog_record
from test.files.fakes import StorageServer

CLIENT = VerifiedIdentity(uuid4(), AppRole.CLIENT)


def test_pagination_is_stable_scoped_and_exhaustible() -> None:
    repository = MemoryCatalogRepository()
    for number in range(1, 5):
        row = catalog_record(UUID(int=number))
        repository.rows[row.id] = row
    storage = StorageServer().adapter()
    try:
        service = CatalogService(repository, storage, 60)
        first = service.list(CLIENT, 2)
        assert [row.id.int for row in first.items] == [1, 2]
        second = service.list(CLIENT, 2, first.next_cursor)
        assert [row.id.int for row in second.items] == [3, 4]
        assert second.next_cursor is None
        empty = service.list(
            CLIENT, 2, encode_cursor("print-catalog", UUID(int=99))
        )
        assert empty.items == () and empty.next_cursor is None
    finally:
        storage.close()


@pytest.mark.parametrize(
    "cursor",
    [
        "not-a-cursor",
        "",
        "x" * 257,
        encode_cursor("prints", UUID(int=1)),
        encode_cursor("print-catalog", "not-uuid"),
        encode_cursor("print-catalog", "00000000000000000000000000000001"),
    ],
)
def test_invalid_cursor_never_queries_database(cursor: str) -> None:
    repository = MemoryCatalogRepository()
    storage = StorageServer().adapter()
    try:
        with pytest.raises(PrintError) as caught:
            CatalogService(repository, storage, 60).list(CLIENT, 20, cursor)
        assert caught.value.failure is PrintFailure.INVALID_CURSOR
        assert repository.calls == 0
    finally:
        storage.close()


@pytest.mark.parametrize("limit", [0, -1, 101, True])
def test_limit_validation_precedes_repository(limit: int) -> None:
    repository = MemoryCatalogRepository()
    storage = StorageServer().adapter()
    try:
        with pytest.raises(PrintError):
            CatalogService(repository, storage, 60).list(CLIENT, limit)
        assert repository.calls == 0
    finally:
        storage.close()


def test_download_requires_current_version_and_only_signs_thumbnail() -> None:
    repository = MemoryCatalogRepository()
    row = catalog_record()
    repository.rows[row.id] = row
    server = StorageServer()
    storage = server.adapter()
    try:
        service = CatalogService(repository, storage, 60)
        with pytest.raises(PrintError) as stale:
            service.create_thumbnail_download(CLIENT, row.id, uuid4())
        assert stale.value.failure is PrintFailure.PRINT_VERSION_NOT_FOUND
        assert server.requests == []
        result = service.create_thumbnail_download(
            CLIENT, row.id, row.version_id
        )
        assert result.file_id == row.thumbnail.id
        assert server.requests[-1].url.path.endswith(row.thumbnail.object_key)
        assert "download_url" not in repr(result)
        repository.rows.clear()
        count = len(server.requests)
        with pytest.raises(PrintError) as hidden:
            service.create_thumbnail_download(CLIENT, row.id, row.version_id)
        assert hidden.value.failure is PrintFailure.PRINT_NOT_FOUND
        assert len(server.requests) == count
    finally:
        storage.close()


@pytest.mark.parametrize("role", [AppRole.CLIENT, AppRole.ADMINISTRATOR])
def test_reader_roles_share_the_same_catalog(role: AppRole) -> None:
    repository = MemoryCatalogRepository()
    row = catalog_record()
    repository.rows[row.id] = row
    server = StorageServer()
    storage = server.adapter()
    try:
        identity = VerifiedIdentity(uuid4(), role)
        service = CatalogService(repository, storage, 60)
        assert service.get(identity, row.id) == row
        assert service.list(identity).items == (row,)
        assert not server.requests
    finally:
        storage.close()
