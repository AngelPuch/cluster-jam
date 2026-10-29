"""Restore snapshots into new, isolated PostgreSQL projects."""

import json
import os
import re
import secrets
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from .runtime import (
    DIRECTORY,
    TABLES,
    OperationError,
    psql,
    revision,
    run,
)

OBJECT_LIMIT = 10_000


def inventory(container: str) -> dict[str, Any]:
    counts = ",".join(
        f"'{name}',(SELECT count(*) FROM app.{name})" for name in TABLES
    )
    result = psql(
        container,
        f"""
        SELECT json_build_object(
          'database',current_database(),'role',current_user,
          'privileged',(SELECT rolsuper OR rolcreatedb OR rolcreaterole
             OR rolreplication OR rolbypassrls FROM pg_roles
             WHERE rolname=current_user),
          'revision',(SELECT version_num FROM app.alembic_version),
          'counts',json_build_object({counts}),
          'objects',(SELECT coalesce(json_agg(items),'[]'::json) FROM (
            SELECT id::text AS id,bucket,objeto_clave AS object_key,
              mime AS mime_type,bytes AS size_bytes,sha256,estado AS state
            FROM app.archivo ORDER BY id LIMIT {OBJECT_LIMIT + 1}
          ) items),
          'tables',(SELECT json_agg(tablename ORDER BY tablename)
            FROM pg_tables WHERE schemaname='app')
        )
    """,
    )
    if (
        result.get("database") != "personalizacion_db"
        or result.get("role") != "app_personalizacion"
        or result.get("privileged") is not False
        or result.get("revision") != revision()
        or result.get("tables") != sorted(TABLES)
    ):
        raise OperationError("SNAPSHOT_SCHEMA_MISMATCH")
    objects = result.get("objects")
    if not isinstance(objects, list) or len(objects) > OBJECT_LIMIT:
        raise OperationError("BACKUP_OBJECT_LIMIT_EXCEEDED")
    return result


def dump_database(container: str, destination: Path) -> None:
    with destination.open("xb") as output:
        run(
            [
                "docker",
                "exec",
                "--user",
                "postgres",
                container,
                "pg_dump",
                "--no-password",
                "--username",
                "app_personalizacion",
                "--dbname",
                "personalizacion_db",
                "--format=custom",
                "--schema=app",
                "--no-owner",
                "--no-privileges",
                "--lock-wait-timeout=15000",
            ],
            output_file=output,
        )
        output.flush()
        os.fsync(output.fileno())


class RecoveryDatabase:
    def __init__(self, image: str, workspace: Path | None = None) -> None:
        self.project = "personalization-recovery-" + uuid4().hex[:12]
        self._temporary: tempfile.TemporaryDirectory[str] | None = None
        if workspace is None:
            self._temporary = tempfile.TemporaryDirectory(prefix=self.project)
            self.directory = Path(self._temporary.name)
        else:
            if workspace.exists() or workspace.is_symlink():
                raise OperationError("RECOVERY_WORKSPACE_MUST_BE_NEW")
            workspace.mkdir(mode=0o700)
            self.directory = workspace
        self._keep = False
        self._started = False
        admin = self.directory / "admin_password"
        application = self.directory / "application_password"
        for path in (admin, application):
            path.write_text(secrets.token_urlsafe(32), encoding="utf-8")
            # The private parent protects files on the host; PostgreSQL
            # reads only these two bind-mounted secrets.
            path.chmod(0o444)
        model = {
            "name": self.project,
            "services": {
                "db-personalizacion": {
                    "image": image,
                    "environment": {
                        "POSTGRES_DB": "personalizacion_db",
                        "POSTGRES_USER": "postgres",
                        "POSTGRES_PASSWORD_FILE": "/run/secrets/admin",
                        "POSTGRES_INITDB_ARGS": "--auth-host=scram-sha-256",
                    },
                    "secrets": ["admin", "personalization_db_password"],
                    "volumes": [
                        "data:/var/lib/postgresql/data",
                        {
                            "type": "bind",
                            "source": str(DIRECTORY / "postgres"),
                            "target": "/docker-entrypoint-initdb.d",
                            "read_only": True,
                        },
                    ],
                    "networks": ["private"],
                    "healthcheck": {
                        "test": [
                            "CMD",
                            "pg_isready",
                            "-U",
                            "postgres",
                            "-d",
                            "personalizacion_db",
                        ],
                        "interval": "2s",
                        "timeout": "2s",
                        "retries": 30,
                    },
                    "mem_limit": "512m",
                    "cpus": 1,
                    "pids_limit": 128,
                }
            },
            "networks": {"private": {"internal": True}},
            "volumes": {"data": {}},
            "secrets": {
                "admin": {"file": str(admin)},
                "personalization_db_password": {"file": str(application)},
            },
        }
        self.configuration = self.directory / "compose.json"
        self.configuration.write_text(json.dumps(model), encoding="utf-8")
        self.command = [
            "docker",
            "compose",
            "-p",
            self.project,
            "-f",
            str(self.configuration),
        ]

    def start(self) -> str:
        self._started = True
        run([*self.command, "up", "-d", "--wait", "--wait-timeout", "90"])
        identifier = (
            run([*self.command, "ps", "--quiet", "db-personalizacion"])
            .decode()
            .strip()
        )
        if re.fullmatch(r"[0-9a-f]{64}", identifier) is None:
            raise OperationError("RECOVERY_DATABASE_UNAVAILABLE")
        return identifier

    def restore(self, dump: Path) -> dict[str, Any]:
        identifier = self.start()
        empty = psql(
            identifier,
            "SELECT json_build_object('tables',count(*)) "
            "FROM pg_tables WHERE schemaname='app'",
        )
        if empty.get("tables") != 0:
            raise OperationError("RECOVERY_DATABASE_NOT_EMPTY")
        with dump.open("rb") as source:
            run(
                [
                    "docker",
                    "exec",
                    "-i",
                    "--user",
                    "postgres",
                    identifier,
                    "pg_restore",
                    "--no-password",
                    "--username",
                    "app_personalizacion",
                    "--dbname",
                    "personalizacion_db",
                    "--schema=app",
                    "--clean",
                    "--if-exists",
                    "--no-owner",
                    "--no-privileges",
                    "--single-transaction",
                ],
                input_file=source,
            )
        return inventory(identifier)

    def retain(self) -> None:
        self._keep = True

    def close(self) -> None:
        if not self._keep and self._started:
            if not re.fullmatch(
                r"personalization-recovery-[0-9a-f]{12}", self.project
            ):
                raise OperationError("UNSAFE_RECOVERY_CLEANUP")
            run([*self.command, "down", "--volumes", "--remove-orphans"])
        if not self._keep and self._temporary is not None:
            self._temporary.cleanup()
