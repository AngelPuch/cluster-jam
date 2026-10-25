"""Represent successful technical health responses."""

from typing import Literal

from personalization.interfaces.http.dto.rest_model import RestModel


class HealthResponse(RestModel):
    """A healthy process or a ready local service."""

    status: Literal["ok"] = "ok"
