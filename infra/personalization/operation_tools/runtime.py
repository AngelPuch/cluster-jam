"""Bound and scope private operator commands to Personalization."""

import ast
import json
import logging
import os
import re
import socket
import subprocess
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

ROOT = Path(__file__).resolve().parents[3]
DIRECTORY = ROOT / "infra" / "personalization"
TABLES = (
    "alembic_version",
    "archivo",
    "estampado",
    "estampado_version",
    "plantilla_version",
    "zona",
    "tamano_zona",
    "diseno",
    "aplicacion",
    "auditoria_local",
)


class OperationError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def revision() -> str:
    source = ROOT / (
        "services/personalizationService/src/personalization/"
        "infrastructure/database/migration_config.py"
    )
    for node in ast.parse(source.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "CURRENT_REVISION"
            for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            if isinstance(value, str):
                return value
    raise OperationError("SCHEMA_REVISION_UNAVAILABLE")


def run(
    arguments: list[str],
    *,
    input_file: BinaryIO | None = None,
    output_file: BinaryIO | None = None,
    timeout: int = 600,
) -> bytes:
    try:
        result = subprocess.run(
            arguments,
            stdin=input_file,
            stdout=output_file if output_file is not None else subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise OperationError("COMMAND_UNAVAILABLE") from None
    if result.returncode:
        raise OperationError("COMMAND_FAILED")
    data = result.stdout if isinstance(result.stdout, bytes) else b""
    if len(data) > 20_000_000:
        raise OperationError("COMMAND_OUTPUT_TOO_LARGE")
    return data


def json_object(data: bytes) -> dict[str, Any]:
    try:
        value: object = json.loads(data)
    except ValueError:
        raise OperationError("INVALID_OPERATION_DATA") from None
    if not isinstance(value, dict):
        raise OperationError("INVALID_OPERATION_DATA")
    return value


def external_location(path: Path) -> Path:
    resolved = path.expanduser().absolute()
    if any(item.is_symlink() for item in (resolved, *resolved.parents)):
        raise OperationError("UNSAFE_BACKUP_DIRECTORY")
    resolved = resolved.resolve()
    if resolved == Path(resolved.anchor) or resolved.is_relative_to(ROOT):
        raise OperationError("BACKUP_DIRECTORY_MUST_BE_EXTERNAL")
    return resolved


def external_directory(path: Path, *, create: bool = False) -> Path:
    resolved = external_location(path)
    if create:
        resolved.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not resolved.is_dir():
        raise OperationError("BACKUP_DIRECTORY_UNAVAILABLE")
    return resolved


class ComposeContext:
    command: list[str]
    gateway: list[str]

    def __init__(self, *, deployment: bool = False) -> None:
        self.deployment = deployment
        if deployment:
            if sys.platform == "win32":
                raise OperationError("DEPLOYMENT_REQUIRES_UBUNTU")
            self.command = [
                "bash",
                str(ROOT / "infra/deploy/compose.sh"),
                "personalization",
            ]
            self.gateway = [
                "bash",
                str(ROOT / "infra/deploy/compose.sh"),
                "shared",
            ]
        else:
            self.command = ["docker", "compose"]
            for name in (
                "compose.yaml",
                "compose.storage.yaml",
                "compose.https.dev.yaml",
            ):
                self.command.extend(["-f", str(DIRECTORY / name)])
            self.gateway = self.command
        self.model = json_object(
            run(
                [
                    *self.command,
                    "--profile",
                    "images",
                    "--profile",
                    "rpc",
                    "--profile",
                    "tools",
                    "config",
                    "--format",
                    "json",
                ]
            )
        )

    def database_id(self) -> str:
        identifier = (
            run(
                [
                    *self.command,
                    "ps",
                    "--status",
                    "running",
                    "--quiet",
                    "db-personalizacion",
                ],
                timeout=30,
            )
            .decode()
            .strip()
        )
        if re.fullmatch(r"[0-9a-f]{64}", identifier) is None:
            raise OperationError("DATABASE_NOT_RUNNING")
        return identifier


def psql(container: str, sql: str) -> dict[str, Any]:
    return json_object(
        run(
            [
                "docker",
                "exec",
                "--user",
                "postgres",
                "--env",
                "PGOPTIONS=-c statement_timeout=15000",
                container,
                "psql",
                "-X",
                "-A",
                "-t",
                "--no-password",
                "--set",
                "ON_ERROR_STOP=1",
                "--username",
                "app_personalizacion",
                "--dbname",
                "personalizacion_db",
                "--command",
                sql,
            ],
            timeout=30,
        )
    )


class JsonFormatter(logging.Formatter):
    def __init__(self, environment: str) -> None:
        super().__init__()
        self._environment = environment

    def format(self, record: logging.LogRecord) -> str:
        project = ROOT / "services/personalizationService/pyproject.toml"
        with project.open("rb") as stream:
            version = tomllib.load(stream)["project"]["version"]
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "service_name": "personalization",
            "service_version": version,
            "environment": self._environment,
            "instance_id": socket.gethostname(),
            "event": record.__dict__.get("event", "operations.completed"),
            "message": record.getMessage(),
            "trace_id": None,
            "span_id": None,
        }
        for name in (
            "code",
            "backup_id",
            "object_count",
            "pending_files",
            "duration_ms",
            "checks",
            "backup_age_seconds",
            "recovery_project",
            "manifest_sha256",
        ):
            if name in record.__dict__:
                payload[name] = record.__dict__[name]
        return json.dumps(payload)


def configure_logging(environment: str = "development") -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(environment))
    logger = logging.getLogger("personalization.operations")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if os.name == "posix":
        os.umask(0o077)
    return logger
