"""Save administrative drafts with unverified Catalog references."""

from uuid import UUID

from personalization.application.designs.design_rules import resolve_targets
from personalization.application.designs.draft_record import (
    DesignCondition,
    DesignState,
    DraftContent,
    DraftPage,
    DraftRecord,
)
from personalization.application.errors.design_error import (
    DesignError,
    DesignFailure,
)
from personalization.application.errors.print_error import PrintError
from personalization.application.ports.design_repository_port import (
    DesignRepositoryPort,
)
from personalization.application.ports.template_repository_port import (
    TemplateRepositoryPort,
)
from personalization.application.prints.cursor import (
    decode_cursor,
    encode_cursor,
)
from personalization.application.prints.print_service import (
    require_administrator,
)
from personalization.application.security.identity import VerifiedIdentity
from personalization.application.templates.template_record import (
    TemplateDefinition,
)
from personalization.application.templates.template_rules import (
    validate_definition,
)


class DraftService:
    def __init__(
        self,
        repository: DesignRepositoryPort,
        templates: TemplateRepositoryPort,
    ) -> None:
        self._repository = repository
        self._templates = templates

    def _validate(self, content: DraftContent) -> DraftContent:
        if (
            not isinstance(content.variant_id, UUID)
            or not isinstance(content.template_id, UUID)
            or len(content.applications) > 20
        ):
            raise DesignError(DesignFailure.INVALID_DESIGN_DATA)
        template = self._templates.get(content.template_id)
        validate_definition(
            TemplateDefinition(
                template.header.front,
                template.header.back,
                tuple(zone.definition for zone in template.zones),
            )
        )
        if content.applications:
            resolve_targets(template, content.applications)
        return content.canonical()

    def create(
        self, identity: VerifiedIdentity, content: DraftContent
    ) -> DraftRecord:
        require_administrator(identity)
        return self._repository.create(
            identity.user_id, self._validate(content)
        )

    def get(self, identity: VerifiedIdentity, design_id: UUID) -> DraftRecord:
        require_administrator(identity)
        return self._repository.get(identity.user_id, design_id)

    def update(
        self,
        identity: VerifiedIdentity,
        design_id: UUID,
        content: DraftContent,
        condition: DesignCondition,
    ) -> DraftRecord:
        require_administrator(identity)
        original = self._repository.get(identity.user_id, design_id)
        if original.state is not DesignState.DRAFT:
            raise DesignError(DesignFailure.DESIGN_NOT_EDITABLE)
        return self._repository.update(
            identity.user_id, design_id, self._validate(content), condition
        )

    def copy(self, identity: VerifiedIdentity, design_id: UUID) -> DraftRecord:
        require_administrator(identity)
        original = self._repository.get(identity.user_id, design_id)
        self._validate(original.content)
        return self._repository.copy(identity.user_id, design_id)

    def list(
        self,
        identity: VerifiedIdentity,
        limit: int = 20,
        cursor: str | None = None,
    ) -> DraftPage:
        require_administrator(identity)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise DesignError(DesignFailure.INVALID_DESIGN_DATA)
        scope = f"admin-design-drafts/{identity.user_id}"
        after = None
        try:
            value = decode_cursor(cursor, scope)
            if value is not None:
                after = UUID(value)
                if str(after) != value:
                    raise ValueError
        except PrintError, ValueError:
            raise DesignError(DesignFailure.INVALID_CURSOR) from None
        rows = self._repository.list(identity.user_id, after, limit + 1)
        items = rows[:limit]
        return DraftPage(
            items,
            encode_cursor(scope, items[-1].id) if len(rows) > limit else None,
        )
