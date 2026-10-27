"""Register the service ORM mappings without executing DDL."""

from .application import ApplicationModel
from .audit_entry import AuditEntryModel
from .base import Base
from .design import DesignModel
from .image_file import FileModel
from .print import PrintModel
from .print_version import PrintVersionModel
from .template_version import TemplateVersionModel
from .zone import ZoneModel
from .zone_size import ZoneSizeModel

__all__ = [
    "ApplicationModel",
    "AuditEntryModel",
    "Base",
    "DesignModel",
    "FileModel",
    "PrintModel",
    "PrintVersionModel",
    "TemplateVersionModel",
    "ZoneModel",
    "ZoneSizeModel",
]
