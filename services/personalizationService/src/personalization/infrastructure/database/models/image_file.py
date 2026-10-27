"""Map archivo using explicit Spanish SQL identifiers."""

from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class FileModel(Base):
    """Persist archivo inside the service database."""

    __tablename__ = "archivo"
    __table_args__ = (
        sa.UniqueConstraint(
            "bucket", "objeto_clave", name="uq_archivo_objeto"
        ),
        sa.CheckConstraint("bytes > 0", name="ck_archivo_bytes"),
        sa.CheckConstraint(
            "ancho_px > 0 AND alto_px > 0", name="ck_archivo_dimensiones"
        ),
        sa.CheckConstraint(
            "sha256 ~ '^[0-9a-f]{64}$'", name="ck_archivo_sha256"
        ),
        sa.CheckConstraint(
            "mime IN ('image/png', 'image/jpeg')", name="ck_archivo_mime"
        ),
        sa.CheckConstraint(
            (
                "btrim(bucket) <> '' AND btrim(objeto_clave) <> "
                "'' AND btrim(uso) <> '' AND btrim(estado) <> ''"
            ),
            name="ck_archivo_textos",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_archivo"),
        sa.Index("ix_archivo_propietario", "propietario_ref", "id"),
    )

    id: Mapped[UUID] = mapped_column(
        "id", sa.Uuid, nullable=False, primary_key=True, default=uuid4
    )
    owner_id: Mapped[UUID] = mapped_column(
        "propietario_ref", sa.Uuid, nullable=False
    )
    bucket: Mapped[str] = mapped_column("bucket", sa.Text, nullable=False)
    object_key: Mapped[str] = mapped_column(
        "objeto_clave", sa.Text, nullable=False
    )
    sha256: Mapped[str] = mapped_column("sha256", sa.CHAR(64), nullable=False)
    mime_type: Mapped[str] = mapped_column("mime", sa.Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(
        "bytes", sa.BigInteger, nullable=False
    )
    width_px: Mapped[int] = mapped_column(
        "ancho_px", sa.Integer, nullable=False
    )
    height_px: Mapped[int] = mapped_column(
        "alto_px", sa.Integer, nullable=False
    )
    usage: Mapped[str] = mapped_column("uso", sa.Text, nullable=False)
    state: Mapped[str] = mapped_column("estado", sa.Text, nullable=False)
