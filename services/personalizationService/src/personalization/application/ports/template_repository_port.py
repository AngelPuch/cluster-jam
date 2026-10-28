"""Persist an immutable template aggregate together with its audit."""

from typing import Protocol
from uuid import UUID

from personalization.application.templates.template_record import (
    TemplateDefinition,
    TemplateHeader,
    TemplateRecord,
)


class TemplateRepositoryPort(Protocol):
    def create(
        self,
        actor_id: UUID,
        product_id: UUID,
        size_id: int,
        expected_version: int,
        definition: TemplateDefinition,
    ) -> TemplateRecord: ...

    def get(self, template_id: UUID) -> TemplateRecord: ...

    def list(
        self,
        product_id: UUID,
        size_id: int,
        after: int | None,
        limit: int,
    ) -> tuple[TemplateHeader, ...]: ...
