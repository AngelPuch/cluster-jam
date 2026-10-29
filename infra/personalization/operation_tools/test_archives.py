"""Protect backup integrity and immutable object recovery."""

import hashlib
import io
import json
from datetime import UTC, datetime
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request
from uuid import uuid4

import pytest

from .bundles import file_digest, verify_bundle
from .objects import StoredObject
from .runtime import (
    ROOT,
    TABLES,
    OperationError,
    configure_logging,
    external_directory,
    revision,
)
from .storage import StorageArchive

TEST_KEY = "sb_secret_" + "test-only-backup-key-" * 2
BUCKET = "personalization-originals"


@pytest.fixture
def entry() -> StoredObject:
    identifier = str(uuid4())
    return StoredObject(
        identifier,
        BUCKET,
        identifier + ".png",
        "image/png",
        7,
        hashlib.sha256(b"fixture").hexdigest(),
        "DISPONIBLE",
    )


@pytest.fixture
def bundle_directory(tmp_path: Path, entry: StoredObject) -> Path:
    directory = tmp_path / "backup"
    (directory / "objects").mkdir(parents=True)
    dump = directory / "database.dump"
    dump.write_bytes(b"PGDMPfixture-only")
    (directory / "objects" / entry.id).write_bytes(b"fixture")
    counts = dict.fromkeys(TABLES, 0)
    counts.update(alembic_version=1, archivo=1)
    metadata = {
        "format_version": 1,
        "backup_id": uuid4().hex,
        "created_at": datetime.now(UTC).isoformat(),
        "schema_revision": revision(),
        "database": "personalizacion_db",
        "database_image": "postgres:17.11-bookworm@sha256:" + "a" * 64,
        "dump_bytes": dump.stat().st_size,
        "dump_sha256": file_digest(dump),
        "row_counts": counts,
        "objects": [entry.mapping()],
        "pending_files": 0,
        "storage_origin": "https://supabase.example.test",
        "bucket": BUCKET,
    }
    (directory / "manifest.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )
    return directory


def test_backup_verifies_database_and_image_hashes(
    bundle_directory: Path,
) -> None:
    bundle = verify_bundle(bundle_directory)
    assert len(bundle.available) == 1
    assert bundle.metadata["row_counts"]["archivo"] == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "../outside"),
        ("object_key", "../outside.png"),
        ("object_key", "another-file.png"),
        ("bucket", "../other"),
        ("size_bytes", True),
        ("size_bytes", 0),
        ("size_bytes", 10_000_001),
        ("mime_type", "text/plain"),
        ("sha256", "not-a-digest"),
        ("state", "unknown"),
        ("id", None),
    ],
)
def test_object_metadata_rejects_unsafe_paths_and_limits(
    entry: StoredObject,
    field: str,
    value: object,
) -> None:
    data = entry.mapping()
    data[field] = value
    with pytest.raises(OperationError):
        StoredObject.from_mapping(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("database", "another_db"),
        ("schema_revision", "future_revision"),
        ("format_version", True),
        ("database_image", "untrusted:latest"),
        ("dump_bytes", True),
        ("dump_bytes", 0),
        ("dump_sha256", "invalid"),
        ("backup_id", "../outside"),
        ("created_at", "invalid"),
        ("created_at", "2026-01-01T00:00:00"),
        ("storage_origin", "http://supabase.example.test"),
        ("storage_origin", "https://user:password@supabase.example.test"),
        ("storage_origin", "https://supabase.example.test/?token=private"),
        ("pending_files", True),
        ("row_counts", {}),
        ("objects", []),
    ],
)
def test_manifest_rejects_incompatible_or_unsafe_backup(
    bundle_directory: Path,
    field: str,
    value: object,
) -> None:
    manifest = bundle_directory / "manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload[field] = value
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(OperationError):
        verify_bundle(bundle_directory)


@pytest.mark.parametrize("target", ["database.dump", "image"])
def test_corrupted_payload_cannot_be_restored(
    bundle_directory: Path,
    entry: StoredObject,
    target: str,
) -> None:
    path = (
        bundle_directory / target
        if target == "database.dump"
        else bundle_directory / "objects" / entry.id
    )
    path.write_bytes(b"changed")
    with pytest.raises(OperationError, match="BACKUP_INTEGRITY_MISMATCH"):
        verify_bundle(bundle_directory)


def test_backup_rejects_extra_files(bundle_directory: Path) -> None:
    (bundle_directory / "objects" / "unexpected").write_bytes(b"private")
    with pytest.raises(OperationError, match="BACKUP_FILE_SET_MISMATCH"):
        verify_bundle(bundle_directory)


def test_backup_rejects_object_symlinks(
    bundle_directory: Path,
    entry: StoredObject,
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.write_bytes(b"fixture")
    path = bundle_directory / "objects" / entry.id
    path.unlink()
    try:
        path.symlink_to(outside)
    except OSError:
        pytest.skip("Creating symlinks requires Windows developer mode")
    with pytest.raises(OperationError):
        verify_bundle(bundle_directory)


def test_backup_cannot_target_the_repository() -> None:
    with pytest.raises(
        OperationError, match="BACKUP_DIRECTORY_MUST_BE_EXTERNAL"
    ):
        external_directory(ROOT, create=True)


class StorageFixture:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.posts = 0
        self.public = False
        self.lose_acknowledgement = False

    def open(self, request: Request, *, timeout: int) -> io.BytesIO:
        assert timeout == 30
        headers = {key.lower(): value for key, value in request.header_items()}
        assert headers["apikey"] == TEST_KEY
        if "/bucket/" in request.full_url:
            return io.BytesIO(
                json.dumps(
                    {
                        "id": BUCKET,
                        "public": self.public,
                        "file_size_limit": 10_000_000,
                        "allowed_mime_types": ["image/png", "image/jpeg"],
                    }
                ).encode()
            )
        key = request.full_url.rsplit("/", 1)[1]
        if request.get_method() == "POST":
            assert headers["x-upsert"] == "false"
            self.posts += 1
            assert isinstance(request.data, bytes)
            self.objects[key] = request.data
            if self.lose_acknowledgement:
                raise URLError("private transport diagnostic")
            return io.BytesIO(json.dumps({"Key": BUCKET + "/" + key}).encode())
        if key not in self.objects:
            raise HTTPError(
                request.full_url,
                404,
                "missing",
                Message(),
                io.BytesIO(b'{"code":"NoSuchKey"}'),
            )
        return io.BytesIO(self.objects[key])


def storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, server: StorageFixture
) -> StorageArchive:
    key = tmp_path / "server-key"
    key.write_text(TEST_KEY, encoding="utf-8")
    archive = StorageArchive("https://supabase.example.test", BUCKET, key)
    monkeypatch.setattr(archive, "_opener", server)
    return archive


def test_recovery_creates_missing_objects_and_is_idempotent(
    tmp_path: Path,
    entry: StoredObject,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = StorageFixture()
    archive = storage(tmp_path, monkeypatch, server)
    archive.ensure_private()
    source = tmp_path / "original"
    source.write_bytes(b"fixture")
    assert archive.restore(entry, source) is True
    assert archive.restore(entry, source) is False
    assert server.posts == 1
    assert server.objects[entry.object_key] == b"fixture"


def test_recovery_never_overwrites_conflicting_objects(
    tmp_path: Path,
    entry: StoredObject,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = StorageFixture()
    server.objects[entry.object_key] = b"changed"
    archive = storage(tmp_path, monkeypatch, server)
    with pytest.raises(OperationError, match="STORAGE_INTEGRITY_MISMATCH"):
        archive.restore(entry, tmp_path / "unread-file")
    assert server.posts == 0
    assert server.objects[entry.object_key] == b"changed"


def test_recovery_resolves_lost_acknowledgement_without_retrying_upload(
    tmp_path: Path,
    entry: StoredObject,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = StorageFixture()
    server.lose_acknowledgement = True
    archive = storage(tmp_path, monkeypatch, server)
    source = tmp_path / "original"
    source.write_bytes(b"fixture")
    assert archive.restore(entry, source) is True
    assert server.posts == 1


def test_public_storage_bucket_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = StorageFixture()
    server.public = True
    with pytest.raises(OperationError, match="STORAGE_BUCKET_UNSAFE"):
        storage(tmp_path, monkeypatch, server).ensure_private()


def test_operation_logs_never_include_unapproved_extra_fields(
    capsys: pytest.CaptureFixture[str],
) -> None:
    logger = configure_logging()
    logger.error(
        "Operator command failed",
        extra={"code": "TEST_ERROR", "server_key": TEST_KEY},
    )
    output = capsys.readouterr().out
    data = json.loads(output)
    assert data["code"] == "TEST_ERROR"
    assert "trace_id" in data and "span_id" in data
    assert TEST_KEY not in output


def test_backup_rejects_its_database_volume_before_creating_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from . import bundles
    from .runtime import ComposeContext

    class SourceContext(ComposeContext):
        def __init__(self) -> None:
            self.model = {
                "services": {"db-personalizacion": {"image": "fixture"}}
            }

        def database_id(self) -> str:
            return "fixture-source"

    volume = tmp_path / "database-volume"
    destination = volume / "backup"
    inspected: list[list[str]] = []

    def mounts(arguments: list[str]) -> bytes:
        inspected.append(arguments)
        assert arguments[:2] == ["docker", "inspect"]
        return json.dumps(
            [
                {
                    "Destination": "/var/lib/postgresql/data",
                    "Source": str(volume),
                }
            ]
        ).encode()

    monkeypatch.setattr(bundles, "run", mounts)
    with pytest.raises(
        OperationError, match="BACKUP_DIRECTORY_INSIDE_DATABASE_VOLUME"
    ):
        bundles.create_backup(SourceContext(), destination)
    assert inspected and not destination.exists()


def test_restoration_cannot_write_into_its_input_backup(
    bundle_directory: Path,
) -> None:
    from .bundles import restore_snapshot

    bundle = verify_bundle(bundle_directory)
    workspace = bundle_directory / "recovery"
    with pytest.raises(
        OperationError, match="RECOVERY_WORKSPACE_INSIDE_BACKUP"
    ):
        restore_snapshot(bundle, workspace)
    assert not workspace.exists()
    assert verify_bundle(bundle_directory).metadata == bundle.metadata


def test_new_backup_cannot_be_nested_in_an_existing_backup(
    bundle_directory: Path,
) -> None:
    from .bundles import create_backup
    from .runtime import ComposeContext

    class UnusedContext(ComposeContext):
        def __init__(self) -> None:
            raise AssertionError("The source must not be contacted")

    context = object.__new__(UnusedContext)
    with pytest.raises(
        OperationError, match="BACKUP_OUTPUT_INSIDE_EXISTING_BACKUP"
    ):
        create_backup(context, bundle_directory / "nested")
    assert not (bundle_directory / "nested").exists()
    verify_bundle(bundle_directory)
