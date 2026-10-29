"""Create immutable private objects with bounded HTTP operations."""

import json
from collections.abc import Callable
from hashlib import sha256
from urllib.parse import parse_qs, urlsplit

import httpx
from pydantic import SecretStr

from personalization.application.errors.file_error import (
    FileError,
    FileFailure,
)
from personalization.application.files.file_record import FileRecord
from personalization.application.images.image_policy import MAX_UPLOAD_BYTES


class SupabaseStorage:
    """Keep the server key inside a dedicated reusable HTTP client."""

    def __init__(
        self,
        project_url: str,
        bucket: str,
        key: SecretStr,
        *,
        transport: httpx.BaseTransport | None = None,
        on_progress: Callable[[], None] | None = None,
    ) -> None:
        self._base_url = project_url.rstrip("/") + "/storage/v1"
        self._bucket = bucket
        self._on_progress = on_progress
        self._client = httpx.Client(
            base_url=self._base_url + "/",
            headers={"apikey": key.get_secret_value()},
            timeout=httpx.Timeout(30, connect=5, pool=5),
            limits=httpx.Limits(
                max_connections=4, max_keepalive_connections=4
            ),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    def _progress(self) -> None:
        if self._on_progress is not None:
            self._on_progress()

    def close(self) -> None:
        """Release outbound connections during service shutdown."""
        self._client.close()

    def _json_request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, object] | None = None,
    ) -> dict[str, object]:
        self._progress()
        try:
            response = self._client.request(method, path, json=body)
            response.raise_for_status()
            result: object = response.json()
        except httpx.HTTPError, ValueError:
            raise FileError(FileFailure.STORAGE_UNAVAILABLE) from None
        self._progress()
        if not isinstance(result, dict):
            raise FileError(FileFailure.STORAGE_UNAVAILABLE)
        return result

    def ensure_private(self) -> None:
        """Reject absent, public, or incorrectly constrained buckets."""
        details = self._json_request("GET", "bucket/" + self._bucket)
        mime_types = details.get("allowed_mime_types")
        if (
            details.get("id") != self._bucket
            or details.get("public") is not False
            or details.get("file_size_limit") != MAX_UPLOAD_BYTES
            or not isinstance(mime_types, list)
            or set(str(value) for value in mime_types)
            != {"image/png", "image/jpeg"}
        ):
            raise FileError(FileFailure.STORAGE_BUCKET_UNSAFE)

    def create_bucket(self) -> None:
        """Create only a missing bucket; never modify an
        existing one.
        """
        try:
            response = self._client.get("bucket/" + self._bucket)
        except httpx.HTTPError:
            raise FileError(FileFailure.STORAGE_UNAVAILABLE) from None
        if response.status_code in (400, 404):
            self._json_request(
                "POST",
                "bucket",
                body={
                    "id": self._bucket,
                    "name": self._bucket,
                    "public": False,
                    "file_size_limit": MAX_UPLOAD_BYTES,
                    "allowed_mime_types": ["image/png", "image/jpeg"],
                },
            )
        elif not response.is_success:
            raise FileError(FileFailure.STORAGE_UNAVAILABLE)
        self.ensure_private()

    def _object_path(self, record: FileRecord) -> str:
        """Restrict the elevated key to canonical service
        object names.
        """
        extension = {"image/png": "png", "image/jpeg": "jpg"}.get(
            record.mime_type
        )
        if (
            record.bucket != self._bucket
            or extension is None
            or record.object_key != f"{record.id}.{extension}"
            or not 1 <= record.size_bytes <= MAX_UPLOAD_BYTES
        ):
            raise FileError(FileFailure.FILE_INTEGRITY_MISMATCH)
        return self._bucket + "/" + record.object_key

    def upload(self, record: FileRecord, content: bytes) -> None:
        """Use create-only semantics and never retry
        uncertain writes.
        """
        path = self._object_path(record)
        if (
            len(content) != record.size_bytes
            or sha256(content).hexdigest() != record.sha256
        ):
            raise FileError(FileFailure.FILE_INTEGRITY_MISMATCH)
        self._progress()
        try:
            response = self._client.post(
                "object/" + path,
                content=content,
                headers={
                    "Content-Type": record.mime_type,
                    "x-upsert": "false",
                    "Cache-Control": "private, no-store",
                },
            )
            response.raise_for_status()
            result: object = response.json()
        except httpx.HTTPError, ValueError:
            raise FileError(FileFailure.STORAGE_UNAVAILABLE) from None
        self._progress()
        if not isinstance(result, dict) or result.get("Key") != path:
            raise FileError(FileFailure.STORAGE_UNAVAILABLE)

    def sign_download(self, record: FileRecord, expires_in: int) -> str:
        """Accept only the expected relative signed-object path."""
        path = "/object/sign/" + self._object_path(record)
        result = self._json_request(
            "POST",
            path.lstrip("/"),
            body={"expiresIn": expires_in},
        )
        signed = result.get("signedURL")
        if (
            not isinstance(signed, str)
            or len(signed) > 8192
            or not signed.isascii()
            or any(character.isspace() for character in signed)
        ):
            raise FileError(FileFailure.STORAGE_UNAVAILABLE)
        parsed = urlsplit(signed)
        query = parse_qs(parsed.query, keep_blank_values=True)
        tokens = query.get("token", [])
        if (
            parsed.scheme
            or parsed.netloc
            or parsed.fragment
            or parsed.path != path
            or set(query) != {"token"}
            or len(tokens) != 1
            or not tokens[0]
        ):
            raise FileError(FileFailure.STORAGE_UNAVAILABLE)
        return self._base_url + signed

    def verify_original(self, record: FileRecord) -> None:
        """Stream a bounded download before publishing a pending row."""
        path = "object/authenticated/" + self._object_path(record)
        digest = sha256()
        count = 0
        self._progress()
        try:
            with self._client.stream("GET", path) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes(chunk_size=65_536):
                    self._progress()
                    count += len(chunk)
                    if count > record.size_bytes or count > MAX_UPLOAD_BYTES:
                        raise FileError(FileFailure.FILE_INTEGRITY_MISMATCH)
                    digest.update(chunk)
        except httpx.HTTPError:
            raise FileError(FileFailure.STORAGE_UNAVAILABLE) from None
        if count != record.size_bytes or digest.hexdigest() != record.sha256:
            raise FileError(FileFailure.FILE_INTEGRITY_MISMATCH)

    def read_verified(
        self, record: FileRecord, *, allow_missing: bool = False
    ) -> bytes | None:
        """Verify bounded bytes and explicit missing-key errors."""
        path = "object/authenticated/" + self._object_path(record)
        content = bytearray()
        self._progress()
        try:
            with self._client.stream("GET", path) as response:
                if allow_missing and response.status_code in (400, 404):
                    # Bound error bodies as well as image bytes.
                    error_body = bytearray()
                    for chunk in response.iter_bytes(chunk_size=4096):
                        error_body.extend(chunk)
                        if len(error_body) > 8192:
                            raise FileError(FileFailure.STORAGE_UNAVAILABLE)
                    error: object = json.loads(error_body)
                    if isinstance(error, dict) and (
                        error.get("code") == "NoSuchKey"
                        or (
                            error.get("error") == "not_found"
                            and str(error.get("statusCode")) == "404"
                        )
                    ):
                        return None
                response.raise_for_status()
                for chunk in response.iter_bytes(chunk_size=65_536):
                    self._progress()
                    content.extend(chunk)
                    if (
                        len(content) > record.size_bytes
                        or len(content) > MAX_UPLOAD_BYTES
                    ):
                        raise FileError(FileFailure.FILE_INTEGRITY_MISMATCH)
        except httpx.HTTPError, ValueError:
            raise FileError(FileFailure.STORAGE_UNAVAILABLE) from None
        result = bytes(content)
        if (
            len(result) != record.size_bytes
            or sha256(result).hexdigest() != record.sha256
        ):
            raise FileError(FileFailure.FILE_INTEGRITY_MISMATCH)
        return result
