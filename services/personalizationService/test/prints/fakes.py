"""Keep a replaceable print port exclusively inside tests."""

from dataclasses import replace
from uuid import UUID, uuid4

from personalization.application.errors.print_error import (
    PrintError,
    PrintFailure,
)
from personalization.application.prints.print_record import (
    PrintRecord,
    PrintVersion,
)


class MemoryPrintRepository:
    def __init__(self) -> None:
        self.records: dict[UUID, PrintRecord] = {}
        self.versions: dict[UUID, list[PrintVersion]] = {}
        self.actors: list[UUID] = []
        self.calls = 0
        self.failure: PrintFailure | None = None

    def _check(self) -> None:
        self.calls += 1
        if self.failure is not None:
            raise PrintError(self.failure)

    def create(
        self,
        actor_id: UUID,
        name: str,
        description: str | None,
        file_id: UUID,
        surcharge_cents: int,
    ) -> PrintRecord:
        self._check()
        print_id = UUID(int=len(self.records) + 1)
        version = PrintVersion(uuid4(), print_id, 1, file_id, surcharge_cents)
        record = PrintRecord(print_id, name, description, True, version)
        self.records[print_id] = record
        self.versions[print_id] = [version]
        self.actors.append(actor_id)
        return record

    def get(self, print_id: UUID) -> PrintRecord:
        self._check()
        if print_id not in self.records:
            raise PrintError(PrintFailure.PRINT_NOT_FOUND)
        return self.records[print_id]

    def create_version(
        self,
        actor_id: UUID,
        print_id: UUID,
        expected_version: int,
        file_id: UUID,
        surcharge_cents: int,
    ) -> PrintVersion:
        record = self.get(print_id)
        if record.latest_version.number != expected_version:
            raise PrintError(PrintFailure.PRINT_VERSION_CONFLICT)
        version = PrintVersion(
            uuid4(), print_id, expected_version + 1, file_id, surcharge_cents
        )
        self.records[print_id] = replace(record, latest_version=version)
        self.versions[print_id].append(version)
        self.actors.append(actor_id)
        return version

    def get_version(
        self,
        print_id: UUID,
        version_id: UUID,
    ) -> PrintVersion:
        self._check()
        for version in self.versions.get(print_id, []):
            if version.id == version_id:
                return version
        raise PrintError(PrintFailure.PRINT_VERSION_NOT_FOUND)

    def list(self, after: UUID | None, limit: int) -> tuple[PrintRecord, ...]:
        self._check()
        return tuple(
            record
            for key, record in sorted(self.records.items())
            if after is None or key > after
        )[:limit]

    def list_versions(
        self,
        print_id: UUID,
        after: int | None,
        limit: int,
    ) -> tuple[PrintVersion, ...]:
        self.get(print_id)
        return tuple(
            row
            for row in self.versions[print_id]
            if after is None or row.number > after
        )[:limit]
