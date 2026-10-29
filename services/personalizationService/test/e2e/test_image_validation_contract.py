"""Check multipart input and safe image errors on test-only routes."""

from io import StringIO
from typing import Annotated, cast
from uuid import UUID

import pytest
from fastapi import Depends, FastAPI, File, UploadFile
from fastapi.testclient import TestClient

from personalization.application.errors.image_validation_error import (
    ImageValidationError,
    ImageValidationFailure,
)
from personalization.application.images.validate_image_service import (
    ValidateImageService,
)
from personalization.application.security.identity import (
    AppRole,
    VerifiedIdentity,
)
from personalization.interfaces.http.dto.rest_model import RestModel
from personalization.interfaces.http.images.dependencies import (
    get_image_validator,
)
from personalization.interfaces.http.security import (
    current_identity,
    require_roles,
)
from test.image_samples import make_image

PATH = "/api/v1/image-validation-fixture"


class ImageResponse(RestModel):
    file_id: UUID
    object_key: str
    mime_type: str
    size_bytes: int
    width_px: int
    height_px: int
    sha256: str


@pytest.fixture
def image_client(client: TestClient) -> TestClient:
    app = cast(FastAPI, client.app)

    def verified_actor() -> VerifiedIdentity:
        return VerifiedIdentity(UUID(int=1), AppRole.CLIENT)

    app.dependency_overrides[current_identity] = verified_actor

    @app.post(PATH)
    def validate(
        source: Annotated[UploadFile, File()],
        validator: Annotated[
            ValidateImageService, Depends(get_image_validator)
        ],
        identity: Annotated[
            VerifiedIdentity,
            Depends(require_roles(AppRole.CLIENT, AppRole.ADMINISTRATOR)),
        ],
    ) -> ImageResponse:
        result = validator.execute(source.file, source.content_type)
        return ImageResponse(
            file_id=result.file_id,
            object_key=result.object_key,
            mime_type=result.mime_type,
            size_bytes=result.size_bytes,
            width_px=result.width_px,
            height_px=result.height_px,
            sha256=result.sha256,
        )

    @app.get(PATH + "/failure/{failure}")
    def fail(failure: ImageValidationFailure) -> None:
        raise ImageValidationError(failure)

    return client


def test_multipart_image_response_uses_trusted_camel_case_metadata(
    image_client: TestClient,
) -> None:
    content = make_image()
    response = image_client.post(
        PATH,
        files={"source": ("../../private-name.php", content, "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "fileId",
        "objectKey",
        "mimeType",
        "sizeBytes",
        "widthPx",
        "heightPx",
        "sha256",
    }
    assert body["objectKey"] == body["fileId"] + ".png"
    assert body["mimeType"] == "image/png"
    assert body["sizeBytes"] == len(content)
    assert body["widthPx"] == 12
    assert body["heightPx"] == 8
    assert "private-name" not in response.text


@pytest.mark.parametrize(
    ("content", "mime", "status", "code"),
    [
        (b"", "image/png", 400, "EMPTY_IMAGE"),
        (b"GIF89a", "image/png", 415, "UNSUPPORTED_IMAGE_TYPE"),
        (make_image(), "image/jpeg", 415, "IMAGE_MIME_MISMATCH"),
        (make_image()[:-12], "image/png", 422, "INVALID_IMAGE"),
        (b"x" * 10_000_001, "image/png", 413, "IMAGE_TOO_LARGE"),
    ],
    ids=["empty", "unsupported", "mime-mismatch", "corrupt", "too-large"],
)
def test_multipart_rejections_keep_safe_problem_details(
    image_client: TestClient,
    http_logs: StringIO,
    content: bytes,
    mime: str,
    status: int,
    code: str,
) -> None:
    response = image_client.post(
        PATH + "?secret=private-query",
        files={"source": ("private-filename.png", content, mime)},
    )
    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert set(body) == {
        "type",
        "title",
        "status",
        "detail",
        "instance",
        "code",
        "traceId",
    }
    assert body["code"] == code
    assert body["instance"] == PATH
    assert body["traceId"] == response.headers["traceparent"].split("-")[1]
    output = response.text + http_logs.getvalue()
    assert "private-filename" not in output
    assert "private-query" not in output


@pytest.mark.parametrize(
    ("failure", "status"),
    [
        (ImageValidationFailure.EMPTY_IMAGE, 400),
        (ImageValidationFailure.IMAGE_TOO_LARGE, 413),
        (ImageValidationFailure.UNSUPPORTED_IMAGE_TYPE, 415),
        (ImageValidationFailure.IMAGE_MIME_MISMATCH, 415),
        (ImageValidationFailure.INVALID_IMAGE, 422),
        (ImageValidationFailure.IMAGE_DIMENSIONS_EXCEEDED, 422),
        (ImageValidationFailure.ANIMATED_IMAGE_NOT_SUPPORTED, 422),
        (ImageValidationFailure.IMAGE_READ_FAILED, 503),
    ],
)
def test_all_image_failures_follow_rfc9457(
    image_client: TestClient,
    failure: ImageValidationFailure,
    status: int,
) -> None:
    response = image_client.get(PATH + "/failure/" + failure.value)
    assert response.status_code == status
    assert response.json()["code"] == failure.value
    assert response.json()["detail"]
    assert response.headers["Cache-Control"] == "no-store"


def test_production_app_exposes_no_temporary_image_route(
    client: TestClient,
) -> None:
    assert client.post(PATH).status_code == 404
    assert set(client.get("/openapi.json").json()["paths"]) == {
        "/api/v1/prints",
        "/api/v1/prints/{printId}",
        "/api/v1/prints/{printId}/versions/{versionId}/thumbnail/download-urls",
        "/api/v1/admin/template-versions",
        "/api/v1/admin/template-versions/{templateId}",
        "/api/v1/admin/template-versions/{templateId}/design-analyses",
        "/api/v1/admin/design-drafts",
        "/api/v1/admin/design-drafts/{designId}",
        "/api/v1/admin/design-drafts/{designId}/copies",
        "/health/live",
        "/health/ready",
        "/api/v1/files",
        "/api/v1/files/{fileId}",
        "/api/v1/files/{fileId}/download-urls",
        "/api/v1/admin/prints",
        "/api/v1/admin/prints/{printId}",
        "/api/v1/admin/prints/{printId}/versions",
        "/api/v1/admin/prints/{printId}/versions/{versionId}",
        "/api/v1/admin/prints/{printId}/versions/{versionId}/thumbnail",
        (
            "/api/v1/admin/prints/{printId}/versions/{versionId}"
            "/thumbnail/download-urls"
        ),
    }
