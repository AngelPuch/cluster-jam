"""Validate canonical object identities from snapshot metadata."""

import re
from dataclasses import asdict, dataclass
from typing import Any, Self
from uuid import UUID

from .runtime import OperationError

MAX_OBJECT_BYTES = 10_000_000


@dataclass(frozen=True)
class StoredObject:
    id: str
    bucket: str
    object_key: str
    mime_type: str
    size_bytes: int
    sha256: str
    state: str

    @classmethod
    def from_mapping(cls, value: object) -> Self:
        if not isinstance(value, dict) or set(value) != {
            "id",
            "bucket",
            "object_key",
            "mime_type",
            "size_bytes",
            "sha256",
            "state",
        }:
            raise OperationError("INVALID_OBJECT_METADATA")
        if any(
            not isinstance(value[name], str)
            for name in value
            if name != "size_bytes"
        ):
            raise OperationError("INVALID_OBJECT_METADATA")
        size = value["size_bytes"]
        extension = {"image/png": "png", "image/jpeg": "jpg"}.get(
            value["mime_type"]
        )
        try:
            canonical_id = str(UUID(value["id"]))
        except ValueError:
            raise OperationError("INVALID_OBJECT_METADATA") from None
        if (
            canonical_id != value["id"]
            or extension is None
            or value["object_key"] != f"{canonical_id}.{extension}"
            or re.fullmatch(
                r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", value["bucket"]
            )
            is None
            or isinstance(size, bool)
            or not isinstance(size, int)
            or not 1 <= size <= MAX_OBJECT_BYTES
            or re.fullmatch(r"[0-9a-f]{64}", value["sha256"]) is None
            or value["state"] not in {"DISPONIBLE", "PENDIENTE_CARGA"}
        ):
            raise OperationError("INVALID_OBJECT_METADATA")
        return cls(**value)

    def mapping(self) -> dict[str, Any]:
        return asdict(self)
