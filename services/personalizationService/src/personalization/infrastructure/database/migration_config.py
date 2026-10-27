"""Locate migrations from source or the installed wheel."""

from pathlib import Path
from typing import TextIO

from alembic.config import Config

CURRENT_REVISION = "0001_personalization"


def migration_config(output: TextIO | None = None) -> Config:
    """Locate revisions without credentials or a working directory."""
    configuration = Config(output_buffer=output)
    configuration.set_main_option(
        "script_location", str(Path(__file__).parent / "migrations")
    )
    return configuration
