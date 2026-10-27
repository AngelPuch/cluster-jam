"""Bound request bodies while leaving authentication before parsing."""

from fastapi import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from personalization.application.errors.file_error import (
    FileError,
    FileFailure,
)
from personalization.application.images.image_policy import MAX_UPLOAD_BYTES

MAX_MULTIPART_BYTES = MAX_UPLOAD_BYTES + 131_072
UPLOAD_PARSE_SECONDS = 30


def check_upload_headers(request: Request) -> None:
    """Check framing after authentication and before
    reading the body.
    """
    content_types = request.headers.getlist("content-type")
    if (
        len(content_types) != 1
        or content_types[0].partition(";")[0].strip().lower()
        != "multipart/form-data"
    ):
        raise FileError(FileFailure.INVALID_MULTIPART)
    lengths = request.headers.getlist("content-length")
    if len(lengths) > 1:
        raise FileError(FileFailure.INVALID_MULTIPART)
    if lengths:
        value = lengths[0]
        if not value.isascii() or not value.isdecimal() or len(value) > 20:
            raise FileError(FileFailure.INVALID_MULTIPART)
        if int(value) > MAX_MULTIPART_BYTES:
            raise FileError(FileFailure.UPLOAD_BODY_TOO_LARGE)


class UploadBodyLimitMiddleware:
    """Count actual chunks, including requests without
    Content-Length.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope.get("path") != "/api/v1/files"
        ):
            await self._app(scope, receive, send)
            return
        consumed = 0

        async def bounded_receive() -> Message:
            nonlocal consumed
            message = await receive()
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > MAX_MULTIPART_BYTES:
                    raise FileError(FileFailure.UPLOAD_BODY_TOO_LARGE)
            return message

        await self._app(scope, bounded_receive, send)
