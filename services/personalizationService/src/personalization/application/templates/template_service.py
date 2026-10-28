"""Authorize draft templates while Catalog compatibility is pending."""

from uuid import UUID

from personalization.application.errors.print_error import PrintError
from personalization.application.errors.template_error import (
    TemplateError,
    TemplateFailure,
)
from personalization.application.ports.template_repository_port import (
    TemplateRepositoryPort,
)
from personalization.application.prints.cursor import (
    decode_cursor,
    encode_cursor,
)
from personalization.application.prints.print_record import MAX_VERSION_NUMBER
from personalization.application.prints.print_service import (
    require_administrator,
)
from personalization.application.security.identity import VerifiedIdentity
from personalization.application.templates.template_record import (
    TemplateDefinition,
    TemplatePage,
    TemplateRecord,
)
from personalization.application.templates.template_rules import (
    validate_definition,
)


def validate_series(product_id: UUID, size_id: int) -> None:
    if (
        not isinstance(product_id, UUID)
        or type(size_id) is not int
        or not 1 <= size_id <= 32767
    ):
        raise TemplateError(TemplateFailure.INVALID_TEMPLATE_DATA)


def series_scope(product_id: UUID, size_id: int) -> str:
    return f"template-versions/{product_id}/{size_id}"


class TemplateService:
    def __init__(self, repository: TemplateRepositoryPort) -> None:
        self._repository = repository

    def create(
        self,
        identity: VerifiedIdentity,
        product_id: UUID,
        size_id: int,
        expected_version: int,
        definition: TemplateDefinition,
    ) -> TemplateRecord:
        require_administrator(identity)
        validate_series(product_id, size_id)
        if (
            type(expected_version) is not int
            or not 0 <= expected_version <= MAX_VERSION_NUMBER
        ):
            raise TemplateError(TemplateFailure.INVALID_TEMPLATE_DATA)
        validate_definition(definition)
        return self._repository.create(
            identity.user_id, product_id, size_id, expected_version, definition
        )

    def get(
        self, identity: VerifiedIdentity, template_id: UUID
    ) -> TemplateRecord:
        require_administrator(identity)
        return self._repository.get(template_id)

    def list(
        self,
        identity: VerifiedIdentity,
        product_id: UUID,
        size_id: int,
        limit: int = 20,
        cursor: str | None = None,
    ) -> TemplatePage:
        require_administrator(identity)
        validate_series(product_id, size_id)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise TemplateError(TemplateFailure.INVALID_TEMPLATE_DATA)
        scope = series_scope(product_id, size_id)
        after = None
        try:
            value = decode_cursor(cursor, scope)
            if value is not None:
                after = int(value)
                if str(after) != value or not 1 <= after <= MAX_VERSION_NUMBER:
                    raise ValueError
        except PrintError, ValueError:
            raise TemplateError(TemplateFailure.INVALID_CURSOR) from None
        rows = self._repository.list(product_id, size_id, after, limit + 1)
        items = rows[:limit]
        return TemplatePage(
            items,
            encode_cursor(scope, items[-1].number)
            if len(rows) > limit
            else None,
        )
