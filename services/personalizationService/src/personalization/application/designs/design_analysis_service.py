"""Analyze draft placement and costs for administrators."""

from uuid import UUID

from personalization.application.designs.analysis_record import (
    AnalysisSelection,
    DesignAnalysis,
    ImageGeometry,
)
from personalization.application.designs.design_rules import (
    analyze_application,
    checked_amount,
    resolve_targets,
)
from personalization.application.errors.design_analysis_error import (
    AnalysisFailure,
    DesignAnalysisError,
)
from personalization.application.ports.design_analysis_ports import (
    AnalysisSourcePort,
    ImageGeometryPort,
)
from personalization.application.ports.template_repository_port import (
    TemplateRepositoryPort,
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


class DesignAnalysisService:
    def __init__(
        self,
        templates: TemplateRepositoryPort,
        sources: AnalysisSourcePort,
        images: ImageGeometryPort,
        minimum_dpi: int | None,
    ) -> None:
        self._templates = templates
        self._sources = sources
        self._images = images
        self._minimum_dpi = minimum_dpi

    def analyze(
        self,
        identity: VerifiedIdentity,
        template_id: UUID,
        selections: tuple[AnalysisSelection, ...],
    ) -> DesignAnalysis:
        require_administrator(identity)
        template = self._templates.get(template_id)
        # Recheck stored geometry before calculating placement.
        validate_definition(
            TemplateDefinition(
                template.header.front,
                template.header.back,
                tuple(zone.definition for zone in template.zones),
            )
        )
        targets = resolve_targets(template, selections)
        sources = self._sources.resolve(selections)
        if len(sources) != len(targets):
            raise DesignAnalysisError(
                AnalysisFailure.ANALYSIS_DATABASE_UNAVAILABLE
            )
        cache: dict[UUID, ImageGeometry] = {}
        applications = []
        total = 0
        expected_total = 0
        for target, source in zip(targets, sources, strict=True):
            # Bound all amounts before reading original bytes.
            expected_total = checked_amount(
                expected_total
                + checked_amount(
                    target.size.definition.surcharge_cents
                    + checked_amount(source.print_surcharge_cents)
                )
            )
        for target, source in zip(targets, sources, strict=True):
            if source.file.id not in cache:
                cache[source.file.id] = self._images.inspect(source.file)
            result = analyze_application(
                target,
                cache[source.file.id],
                source.print_surcharge_cents,
                self._minimum_dpi,
            )
            total = checked_amount(total + result.total_surcharge_cents)
            applications.append(result)
        return DesignAnalysis(
            template.header.id,
            template.header.active,
            self._minimum_dpi,
            tuple(applications),
            total,
        )
