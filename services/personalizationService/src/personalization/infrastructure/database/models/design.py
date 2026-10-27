"""Map diseno using explicit Spanish SQL identifiers."""

from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DesignModel(Base):
    """Persist diseno inside the service database."""

    __tablename__ = "diseno"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["plantilla_id"],
            ["app.plantilla_version.id"],
            name="fk_diseno_plantilla",
        ),
        sa.ForeignKeyConstraint(
            ["previa_frente_id"],
            ["app.archivo.id"],
            name="fk_diseno_previa_frente",
        ),
        sa.ForeignKeyConstraint(
            ["previa_espalda_id"],
            ["app.archivo.id"],
            name="fk_diseno_previa_espalda",
        ),
        sa.CheckConstraint("version > 0", name="ck_diseno_version"),
        sa.CheckConstraint("btrim(estado) <> ''", name="ck_diseno_estado"),
        sa.PrimaryKeyConstraint("id", name="pk_diseno"),
        sa.Index("ix_diseno_usuario", "usuario_ref", "id"),
        sa.Index("ix_diseno_plantilla", "plantilla_id"),
        sa.Index("ix_diseno_previa_frente", "previa_frente_id"),
        sa.Index("ix_diseno_previa_espalda", "previa_espalda_id"),
    )

    id: Mapped[UUID] = mapped_column(
        "id", sa.Uuid, nullable=False, primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        "usuario_ref", sa.Uuid, nullable=False
    )
    variant_id: Mapped[UUID] = mapped_column(
        "variante_ref", sa.Uuid, nullable=False
    )
    template_id: Mapped[UUID] = mapped_column(
        "plantilla_id", sa.Uuid, nullable=False
    )
    state: Mapped[str] = mapped_column("estado", sa.Text, nullable=False)
    version: Mapped[int] = mapped_column("version", sa.Integer, nullable=False)
    front_preview_id: Mapped[UUID | None] = mapped_column(
        "previa_frente_id", sa.Uuid, nullable=True
    )
    back_preview_id: Mapped[UUID | None] = mapped_column(
        "previa_espalda_id", sa.Uuid, nullable=True
    )
