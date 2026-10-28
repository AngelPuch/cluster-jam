"""Report calculation failures without provider or database details."""

from enum import StrEnum


class AnalysisFailure(StrEnum):
    INVALID_DESIGN_ANALYSIS = "INVALID_DESIGN_ANALYSIS"
    ZONE_NOT_IN_TEMPLATE = "ZONE_NOT_IN_TEMPLATE"
    SIZE_NOT_IN_ZONE = "SIZE_NOT_IN_ZONE"
    DUPLICATE_ZONE_APPLICATION = "DUPLICATE_ZONE_APPLICATION"
    ANALYSIS_SOURCE_NOT_FOUND = "ANALYSIS_SOURCE_NOT_FOUND"
    ANALYSIS_SOURCE_NOT_READY = "ANALYSIS_SOURCE_NOT_READY"
    INVALID_IMAGE_GEOMETRY = "INVALID_IMAGE_GEOMETRY"
    PERSONALIZATION_AMOUNT_OVERFLOW = "PERSONALIZATION_AMOUNT_OVERFLOW"
    ANALYSIS_DATABASE_UNAVAILABLE = "ANALYSIS_DATABASE_UNAVAILABLE"


class DesignAnalysisError(Exception):
    def __init__(self, failure: AnalysisFailure) -> None:
        super().__init__(failure.value)
        self.failure = failure
