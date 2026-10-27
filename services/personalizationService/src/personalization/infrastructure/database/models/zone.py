"""Map zona using explicit Spanish SQL identifiers."""

from decimal import Decimal
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ZoneModel(Base):
    """Persist zona inside the service database."""

    __tablename__ = "zona"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["plantilla_id"],
            ["app.plantilla_version.id"],
            name="fk_zona_plantilla",
        ),
        sa.UniqueConstraint(
            "plantilla_id", "cara", "codigo", name="uq_zona_codigo"
        ),
        sa.CheckConstraint(
            "cara IN ('FRENTE', 'ESPALDA')", name="ck_zona_cara"
        ),
        sa.CheckConstraint("btrim(codigo) <> ''", name="ck_zona_codigo"),
        sa.CheckConstraint(
            (
                "x_mm >= 0 AND x_mm < 'Infinity'::numeric AND "
                "y_mm >= 0 AND y_mm < 'Infinity'::numeric AND "
                "ancho_mm > 0 AND ancho_mm < 'Infinity'::numeric "
                "AND alto_mm > 0 AND alto_mm < "
                "'Infinity'::numeric"
            ),
            name="ck_zona_geometria",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_zona"),
    )

    id: Mapped[UUID] = mapped_column(
        "id", sa.Uuid, nullable=False, primary_key=True, default=uuid4
    )
    template_id: Mapped[UUID] = mapped_column(
        "plantilla_id", sa.Uuid, nullable=False
    )
    code: Mapped[str] = mapped_column("codigo", sa.String(40), nullable=False)
    side: Mapped[str] = mapped_column("cara", sa.Text, nullable=False)
    x_mm: Mapped[Decimal] = mapped_column("x_mm", sa.Numeric(), nullable=False)
    y_mm: Mapped[Decimal] = mapped_column("y_mm", sa.Numeric(), nullable=False)
    width_mm: Mapped[Decimal] = mapped_column(
        "ancho_mm", sa.Numeric(), nullable=False
    )
    height_mm: Mapped[Decimal] = mapped_column(
        "alto_mm", sa.Numeric(), nullable=False
    )
