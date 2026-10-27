"""Map estampado_version using explicit Spanish SQL identifiers."""

from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PrintVersionModel(Base):
    """Persist estampado_version inside the service database."""

    __tablename__ = "estampado_version"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["estampado_id"],
            ["app.estampado.id"],
            name="fk_estampado_version_estampado",
        ),
        sa.ForeignKeyConstraint(
            ["archivo_id"],
            ["app.archivo.id"],
            name="fk_estampado_version_archivo",
        ),
        sa.UniqueConstraint(
            "estampado_id", "numero", name="uq_estampado_version_numero"
        ),
        sa.CheckConstraint("numero > 0", name="ck_estampado_version_numero"),
        sa.CheckConstraint(
            "recargo_centavos >= 0", name="ck_estampado_version_recargo"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_estampado_version"),
        sa.Index("ix_estampado_version_archivo", "archivo_id"),
    )

    id: Mapped[UUID] = mapped_column(
        "id", sa.Uuid, nullable=False, primary_key=True, default=uuid4
    )
    print_id: Mapped[UUID] = mapped_column(
        "estampado_id", sa.Uuid, nullable=False
    )
    number: Mapped[int] = mapped_column("numero", sa.Integer, nullable=False)
    file_id: Mapped[UUID] = mapped_column(
        "archivo_id", sa.Uuid, nullable=False
    )
    surcharge_cents: Mapped[int] = mapped_column(
        "recargo_centavos", sa.BigInteger, nullable=False
    )
