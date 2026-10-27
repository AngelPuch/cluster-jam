"""Represent the minimal trusted actor for an application operation."""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class AppRole(StrEnum):
    """Use the exact protected application roles defined by Auth."""

    CLIENT = "cliente"
    ADMINISTRATOR = "administrador"


@dataclass(frozen=True)
class VerifiedIdentity:
    """Keep a trusted user ID and role without credentials."""

    user_id: UUID
    app_role: AppRole
