"""Require atomic version writes together with local audit entries."""

from typing import Protocol
from uuid import UUID

from personalization.application.prints.print_changes import (
    PrintChanges,
    PrintCondition,
)
from personalization.application.prints.print_record import (
    PrintRecord,
    PrintVersion,
)


class PrintRepositoryPort(Protocol):
    def create(
        self,
        actor_id: UUID,
        name: str,
        description: str | None,
        file_id: UUID,
        surcharge_cents: int,
    ) -> PrintRecord: ...

    def create_version(
        self,
        actor_id: UUID,
        print_id: UUID,
        expected_version: int,
        file_id: UUID,
        surcharge_cents: int,
    ) -> PrintVersion: ...

    def update(
        self,
        actor_id: UUID,
        print_id: UUID,
        changes: PrintChanges,
        condition: PrintCondition,
    ) -> PrintRecord: ...

    def get(self, print_id: UUID) -> PrintRecord: ...

    def get_version(
        self,
        print_id: UUID,
        version_id: UUID,
    ) -> PrintVersion: ...

    def list(
        self, after: UUID | None, limit: int
    ) -> tuple[PrintRecord, ...]: ...

    def list_versions(
        self,
        print_id: UUID,
        after: int | None,
        limit: int,
    ) -> tuple[PrintVersion, ...]: ...
