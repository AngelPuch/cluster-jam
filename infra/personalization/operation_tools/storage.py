"""Copy immutable Storage bytes without logging keys or signed URLs."""

import hashlib
import json
import os
import re
import ssl
from pathlib import Path
from typing import IO, BinaryIO
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    ProxyHandler,
    Request,
    build_opener,
)

from .objects import MAX_OBJECT_BYTES, StoredObject
from .runtime import OperationError


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self,
        request: Request,
        response: IO[bytes],
        code: int,
        message: str,
        headers: object,
        new_url: str,
    ) -> None:
        return None


class StorageArchive:
    def __init__(self, origin: str, bucket: str, key_file: Path) -> None:
        parsed = urlsplit(origin)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
            or re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", bucket) is None
            or key_file.is_symlink()
        ):
            raise OperationError("INVALID_STORAGE_CONFIGURATION")
        try:
            with key_file.open("r", encoding="utf-8") as stream:
                key = stream.read(1024).rstrip("\r\n")
        except (OSError, UnicodeError):
            raise OperationError("STORAGE_KEY_UNAVAILABLE") from None
        if re.fullmatch(r"sb_secret_[A-Za-z0-9_-]{20,200}", key) is None:
            raise OperationError("INVALID_STORAGE_CONFIGURATION")
        self.origin = origin.rstrip("/")
        self.bucket = bucket
        self._key = key
        self._opener = build_opener(
            ProxyHandler({}),
            HTTPSHandler(context=ssl.create_default_context()),
            NoRedirect(),
        )

    def _request(
        self,
        method: str,
        path: str,
        content: bytes | None = None,
        mime_type: str | None = None,
    ) -> Request:
        headers = {"apikey": self._key, "Cache-Control": "no-store"}
        if content is not None:
            headers.update(
                {
                    "Content-Type": mime_type or "application/octet-stream",
                    "x-upsert": "false",
                }
            )
        return Request(
            self.origin + "/storage/v1/" + path,
            data=content,
            headers=headers,
            method=method,
        )

    def ensure_private(self) -> None:
        try:
            with self._opener.open(
                self._request("GET", "bucket/" + self.bucket), timeout=30
            ) as response:
                content = response.read(16_385)
            value: object = json.loads(content)
        except (HTTPError, URLError, OSError, ValueError):
            raise OperationError("STORAGE_UNAVAILABLE") from None
        if (
            len(content) > 16_384
            or not isinstance(value, dict)
            or value.get("id") != self.bucket
            or value.get("public") is not False
            or value.get("file_size_limit") != MAX_OBJECT_BYTES
            or not isinstance(value.get("allowed_mime_types"), list)
            or set(str(item) for item in value["allowed_mime_types"])
            != {"image/png", "image/jpeg"}
        ):
            raise OperationError("STORAGE_BUCKET_UNSAFE")

    def _read(
        self,
        entry: StoredObject,
        target: BinaryIO | None,
        *,
        allow_missing: bool = False,
    ) -> bool:
        StoredObject.from_mapping(entry.mapping())
        if entry.bucket != self.bucket:
            raise OperationError("STORAGE_BUCKET_MISMATCH")
        count = 0
        digest = hashlib.sha256()
        try:
            request = self._request(
                "GET", f"object/authenticated/{self.bucket}/{entry.object_key}"
            )
            with self._opener.open(request, timeout=30) as response:
                while chunk := response.read(65_536):
                    count += len(chunk)
                    if count > entry.size_bytes:
                        raise OperationError("STORAGE_INTEGRITY_MISMATCH")
                    digest.update(chunk)
                    if target is not None:
                        target.write(chunk)
        except HTTPError as error:
            try:
                status = error.code
                body: object = json.loads(error.read(8193))
            except ValueError:
                body = None
            finally:
                error.close()
            if (
                allow_missing
                and status in {400, 404}
                and isinstance(body, dict)
                and (
                    body.get("code") == "NoSuchKey"
                    or (
                        body.get("error") == "not_found"
                        and str(body.get("statusCode")) == "404"
                    )
                )
            ):
                return False
            raise OperationError("STORAGE_UNAVAILABLE") from None
        except (URLError, OSError):
            raise OperationError("STORAGE_UNAVAILABLE") from None
        if count != entry.size_bytes or digest.hexdigest() != entry.sha256:
            raise OperationError("STORAGE_INTEGRITY_MISMATCH")
        return True

    def download(self, entry: StoredObject, destination: Path) -> None:
        with destination.open("xb") as output:
            self._read(entry, output)
            output.flush()
            os.fsync(output.fileno())

    def restore(self, entry: StoredObject, source: Path) -> bool:
        if self._read(entry, None, allow_missing=True):
            return False
        with source.open("rb") as stream:
            content = stream.read(MAX_OBJECT_BYTES + 1)
        if (
            len(content) != entry.size_bytes
            or hashlib.sha256(content).hexdigest() != entry.sha256
        ):
            raise OperationError("BACKUP_INTEGRITY_MISMATCH")
        request = self._request(
            "POST",
            f"object/{self.bucket}/{entry.object_key}",
            content,
            entry.mime_type,
        )
        try:
            with self._opener.open(request, timeout=30) as response:
                body = response.read(8193)
            result: object = json.loads(body)
            if (
                len(body) > 8192
                or not isinstance(result, dict)
                or result.get("Key") != f"{self.bucket}/{entry.object_key}"
            ):
                raise OperationError("STORAGE_RESTORE_UNCERTAIN")
        except HTTPError as error:
            error.close()
            # Resolve lost acknowledgements through verified reads.
            # Never retry an uncertain create and never enable upsert.
            if not self._read(entry, None, allow_missing=True):
                raise OperationError("STORAGE_RESTORE_UNCERTAIN") from None
        except (URLError, OSError, ValueError):
            if not self._read(entry, None, allow_missing=True):
                raise OperationError("STORAGE_RESTORE_UNCERTAIN") from None
        self._read(entry, None)
        return True
