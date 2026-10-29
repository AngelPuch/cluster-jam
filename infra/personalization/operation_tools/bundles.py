"""Publish and verify database-plus-object recovery bundles."""

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from .database import OBJECT_LIMIT, RecoveryDatabase, dump_database
from .objects import StoredObject
from .runtime import (
    TABLES,
    ComposeContext,
    OperationError,
    external_directory,
    external_location,
    json_object,
    revision,
    run,
)
from .storage import StorageArchive

MAX_BACKUP_BYTES = 10_000_000_000


def file_digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise OperationError("BACKUP_FILE_UNSAFE")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(65_536):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class BackupBundle:
    directory: Path
    metadata: dict[str, Any]
    objects: tuple[StoredObject, ...]

    @property
    def available(self) -> tuple[StoredObject, ...]:
        return tuple(
            item for item in self.objects if item.state == "DISPONIBLE"
        )


def verify_bundle(directory: Path) -> BackupBundle:
    directory = external_directory(directory)
    manifest = directory / "manifest.json"
    if manifest.is_symlink() or manifest.stat().st_size > 20_000_000:
        raise OperationError("INVALID_BACKUP_MANIFEST")
    metadata = json_object(manifest.read_bytes())
    if set(metadata) != {
        "format_version",
        "backup_id",
        "created_at",
        "schema_revision",
        "database",
        "database_image",
        "dump_bytes",
        "dump_sha256",
        "row_counts",
        "objects",
        "pending_files",
        "storage_origin",
        "bucket",
    }:
        raise OperationError("INVALID_BACKUP_MANIFEST")
    counts = metadata["row_counts"]
    objects = metadata["objects"]
    origin = metadata["storage_origin"]
    if (
        metadata["format_version"] != 1
        or isinstance(metadata["format_version"], bool)
        or metadata["schema_revision"] != revision()
        or metadata["database"] != "personalizacion_db"
        or not isinstance(metadata["backup_id"], str)
        or re.fullmatch(r"[0-9a-f]{32}", metadata["backup_id"]) is None
        or not isinstance(metadata["database_image"], str)
        or re.fullmatch(
            r"postgres:17\.[0-9]+-[a-z0-9.-]+@sha256:[0-9a-f]{64}",
            metadata["database_image"],
        )
        is None
        or not isinstance(metadata["dump_sha256"], str)
        or re.fullmatch(r"[0-9a-f]{64}", metadata["dump_sha256"]) is None
        or isinstance(metadata["dump_bytes"], bool)
        or not isinstance(metadata["dump_bytes"], int)
        or not 5 < metadata["dump_bytes"] <= MAX_BACKUP_BYTES
        or not isinstance(counts, dict)
        or set(counts) != set(TABLES)
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in counts.values()
        )
        or counts["alembic_version"] != 1
        or not isinstance(objects, list)
        or len(objects) > OBJECT_LIMIT
        or not isinstance(origin, str)
        or not isinstance(metadata["bucket"], str)
    ):
        raise OperationError("INVALID_BACKUP_MANIFEST")
    try:
        created = datetime.fromisoformat(metadata["created_at"])
        parsed = urlsplit(origin)
    except (TypeError, ValueError):
        raise OperationError("INVALID_BACKUP_MANIFEST") from None
    if (
        created.tzinfo is None
        or parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise OperationError("INVALID_BACKUP_MANIFEST")
    entries = tuple(StoredObject.from_mapping(value) for value in objects)
    if (
        len({entry.id for entry in entries}) != len(entries)
        or counts["archivo"] != len(entries)
        or any(entry.bucket != metadata["bucket"] for entry in entries)
        or isinstance(metadata["pending_files"], bool)
        or metadata["pending_files"]
        != sum(entry.state == "PENDIENTE_CARGA" for entry in entries)
    ):
        raise OperationError("INVALID_BACKUP_MANIFEST")
    bundle = BackupBundle(directory, metadata, entries)
    expected = {item.id for item in bundle.available}
    object_directory = directory / "objects"
    if (
        object_directory.is_symlink()
        or not object_directory.is_dir()
        or {item.name for item in object_directory.iterdir()} != expected
        or {item.name for item in directory.iterdir()}
        != {"manifest.json", "database.dump", "objects"}
    ):
        raise OperationError("BACKUP_FILE_SET_MISMATCH")
    dump = directory / "database.dump"
    if (
        dump.is_symlink()
        or not dump.is_file()
        or dump.stat().st_size != metadata["dump_bytes"]
    ):
        raise OperationError("BACKUP_INTEGRITY_MISMATCH")
    with dump.open("rb") as stream:
        if stream.read(5) != b"PGDMP":
            raise OperationError("BACKUP_INTEGRITY_MISMATCH")
    if file_digest(dump) != metadata["dump_sha256"]:
        raise OperationError("BACKUP_INTEGRITY_MISMATCH")
    total_bytes = metadata["dump_bytes"]
    for entry in bundle.available:
        path = object_directory / entry.id
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size != entry.size_bytes
        ):
            raise OperationError("BACKUP_INTEGRITY_MISMATCH")
        total_bytes += entry.size_bytes
        if total_bytes > MAX_BACKUP_BYTES or file_digest(path) != entry.sha256:
            raise OperationError("BACKUP_INTEGRITY_MISMATCH")
    return bundle


def storage_client(context: ComposeContext) -> StorageArchive:
    environment = context.model["services"]["personalization"]["environment"]
    issuer = environment["SUPABASE_ISSUER"]
    if not isinstance(issuer, str) or not issuer.endswith("/auth/v1"):
        raise OperationError("INVALID_STORAGE_CONFIGURATION")
    key = context.model["secrets"]["supabase_storage_key"]["file"]
    return StorageArchive(
        issuer.removesuffix("/auth/v1"),
        environment["SUPABASE_STORAGE_BUCKET"],
        Path(key),
    )


def create_backup(context: ComposeContext, output: Path) -> BackupBundle:
    output = external_location(output)
    if any(
        (item / "manifest.json").is_file()
        and (item / "database.dump").is_file()
        for item in (output, *output.parents)
    ):
        raise OperationError("BACKUP_OUTPUT_INSIDE_EXISTING_BACKUP")
    backup_id = uuid4().hex
    snapshot_started = datetime.now(UTC).isoformat()
    image = context.model["services"]["db-personalizacion"]["image"]
    container = context.database_id()
    mounts: object = json.loads(
        run(["docker", "inspect", "--format", "{{json .Mounts}}", container])
    )
    if not isinstance(mounts, list):
        raise OperationError("DATABASE_MOUNTS_UNAVAILABLE")
    for mount in mounts:
        if (
            isinstance(mount, dict)
            and mount.get("Destination") == "/var/lib/postgresql/data"
        ):
            location = Path(str(mount["Source"])).resolve()
            if output.is_relative_to(location):
                raise OperationError("BACKUP_DIRECTORY_INSIDE_DATABASE_VOLUME")
    output = external_directory(output, create=True)
    with tempfile.TemporaryDirectory(
        prefix=".personalization-backup-", dir=output
    ) as temporary:
        staging = Path(temporary)
        dump = staging / "database.dump"
        dump_database(container, dump)
        recovery = RecoveryDatabase(image)
        try:
            snapshot = recovery.restore(dump)
        finally:
            recovery.close()
        entries = tuple(
            StoredObject.from_mapping(value) for value in snapshot["objects"]
        )
        available = tuple(
            entry for entry in entries if entry.state == "DISPONIBLE"
        )
        if (
            dump.stat().st_size + sum(entry.size_bytes for entry in available)
            > MAX_BACKUP_BYTES
        ):
            raise OperationError("BACKUP_SIZE_LIMIT_EXCEEDED")
        objects = staging / "objects"
        objects.mkdir(mode=0o700)
        if available:
            storage = storage_client(context)
            storage.ensure_private()
            for entry in available:
                storage.download(entry, objects / entry.id)
        environment = context.model["services"]["personalization"][
            "environment"
        ]
        metadata = {
            "format_version": 1,
            "backup_id": backup_id,
            "created_at": snapshot_started,
            "schema_revision": revision(),
            "database": "personalizacion_db",
            "database_image": image,
            "dump_bytes": dump.stat().st_size,
            "dump_sha256": file_digest(dump),
            "row_counts": snapshot["counts"],
            "objects": [entry.mapping() for entry in entries],
            "pending_files": sum(
                entry.state == "PENDIENTE_CARGA" for entry in entries
            ),
            "storage_origin": environment["SUPABASE_ISSUER"].removesuffix(
                "/auth/v1"
            ),
            "bucket": environment["SUPABASE_STORAGE_BUCKET"],
        }
        with (staging / "manifest.json").open("x", encoding="utf-8") as stream:
            json.dump(metadata, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        verify_bundle(staging)
        destination = output / ("personalization-" + backup_id)
        if not staging.resolve().is_relative_to(
            output
        ) or not destination.resolve().is_relative_to(output):
            raise OperationError("UNSAFE_BACKUP_DIRECTORY")
        staging.rename(destination)
    return verify_bundle(destination)


def restore_snapshot(
    bundle: BackupBundle, workspace: Path | None = None
) -> str:
    if workspace is not None:
        parent = external_directory(workspace.parent)
        workspace = parent / workspace.name
        if workspace.resolve().is_relative_to(bundle.directory):
            raise OperationError("RECOVERY_WORKSPACE_INSIDE_BACKUP")
        if workspace.exists() or workspace.is_symlink():
            raise OperationError("RECOVERY_WORKSPACE_MUST_BE_NEW")
    recovery = RecoveryDatabase(bundle.metadata["database_image"], workspace)
    try:
        snapshot = recovery.restore(bundle.directory / "database.dump")
        if snapshot["counts"] != bundle.metadata["row_counts"] or snapshot[
            "objects"
        ] != [entry.mapping() for entry in bundle.objects]:
            raise OperationError("RESTORED_SNAPSHOT_MISMATCH")
        if workspace is not None:
            # Stop the candidate before preparing a volume cutover.
            run([*recovery.command, "stop", "db-personalizacion"])
            overlay = {
                "services": {
                    "db-personalizacion": {
                        "image": bundle.metadata["database_image"]
                    }
                },
                "volumes": {
                    "personalization-data": {
                        "external": True,
                        "name": recovery.project + "_data",
                    }
                },
                "secrets": {
                    "personalization_db_admin_password": {
                        "file": str(workspace / "admin_password")
                    },
                    "personalization_db_password": {
                        "file": str(workspace / "application_password")
                    },
                },
            }
            (workspace / "recovery.override.yaml").write_text(
                json.dumps(overlay, indent=2), encoding="utf-8"
            )
            recovery.retain()
        return recovery.project
    finally:
        recovery.close()


def restore_objects(bundle: BackupBundle, context: ComposeContext) -> int:
    if not bundle.available:
        return 0
    storage = storage_client(context)
    if storage.origin != bundle.metadata["storage_origin"]:
        raise OperationError("STORAGE_PROJECT_MISMATCH")
    storage.ensure_private()
    restored = 0
    for entry in bundle.available:
        restored += storage.restore(
            entry, bundle.directory / "objects" / entry.id
        )
    return restored
