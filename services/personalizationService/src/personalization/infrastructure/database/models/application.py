"""Map aplicacion using explicit Spanish SQL identifiers."""

from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ApplicationModel(Base):
    """Persist aplicacion inside the service database."""

    __tablename__ = "aplicacion"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["diseno_id"], ["app.diseno.id"], name="fk_aplicacion_diseno"
        ),
        sa.ForeignKeyConstraint(
            ["zona_id"], ["app.zona.id"], name="fk_aplicacion_zona"
        ),
        sa.ForeignKeyConstraint(
            ["tamano_id", "zona_id"],
            ["app.tamano_zona.id", "app.tamano_zona.zona_id"],
            name="fk_aplicacion_tamano_zona",
        ),
        sa.ForeignKeyConstraint(
            ["estampado_version_id"],
            ["app.estampado_version.id"],
            name="fk_aplicacion_estampado",
        ),
        sa.ForeignKeyConstraint(
            ["archivo_usuario_id"],
            ["app.archivo.id"],
            name="fk_aplicacion_archivo",
        ),
        sa.UniqueConstraint(
            "diseno_id", "zona_id", name="uq_aplicacion_diseno_zona"
        ),
        sa.CheckConstraint(
            (
                "(estampado_version_id IS NOT NULL) <> "
                "(archivo_usuario_id IS NOT NULL)"
            ),
            name="ck_aplicacion_origen_exclusivo",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_aplicacion"),
        sa.Index("ix_aplicacion_zona", "zona_id"),
        sa.Index("ix_aplicacion_tamano_zona", "tamano_id", "zona_id"),
        sa.Index("ix_aplicacion_estampado", "estampado_version_id"),
        sa.Index("ix_aplicacion_archivo", "archivo_usuario_id"),
    )

    id: Mapped[UUID] = mapped_column(
        "id", sa.Uuid, nullable=False, primary_key=True, default=uuid4
    )
    design_id: Mapped[UUID] = mapped_column(
        "diseno_id", sa.Uuid, nullable=False
    )
    zone_id: Mapped[UUID] = mapped_column("zona_id", sa.Uuid, nullable=False)
    zone_size_id: Mapped[UUID] = mapped_column(
        "tamano_id", sa.Uuid, nullable=False
    )
    print_version_id: Mapped[UUID | None] = mapped_column(
        "estampado_version_id", sa.Uuid, nullable=True
    )
    user_file_id: Mapped[UUID | None] = mapped_column(
        "archivo_usuario_id", sa.Uuid, nullable=True
    )
