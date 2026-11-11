"""Index private derived-file lookups without changing domain tables.

Revision ID: 0002_file_lookup
Revises: 0001_personalization
"""

from alembic import op

revision = "0002_file_lookup"
down_revision = "0001_personalization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Avoid scanning all originals for each catalog thumbnail."""
    op.create_index(
        "ix_archivo_bucket_uso_estado",
        "archivo",
        ["bucket", "uso", "estado"],
        schema="app",
    )


def downgrade() -> None:
    """Remove only the lookup index, preserving all file metadata."""
    op.drop_index(
        "ix_archivo_bucket_uso_estado", table_name="archivo", schema="app"
    )
