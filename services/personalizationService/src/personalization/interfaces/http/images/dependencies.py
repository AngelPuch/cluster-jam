"""Resolve the image validator composed once for each application."""

from typing import cast

from fastapi import Request

from personalization.application.images.validate_image_service import (
    ValidateImageService,
)


def get_image_validator(request: Request) -> ValidateImageService:
    """Keep HTTP routes independent from the Pillow implementation."""
    return cast(ValidateImageService, request.app.state.image_validator)
