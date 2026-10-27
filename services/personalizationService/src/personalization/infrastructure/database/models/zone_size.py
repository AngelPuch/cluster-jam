"""Map tamano_zona using explicit Spanish SQL identifiers."""

from decimal import Decimal
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ZoneSizeModel(Base):
    """Persist tamano_zona inside the service database."""

    __tablename__ = "tamano_zona"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["zona_id"], ["app.zona.id"], name="fk_tamano_zona_zona"
        ),
        sa.UniqueConstraint(
            "zona_id", "etiqueta", name="uq_tamano_zona_etiqueta"
        ),
        sa.UniqueConstraint("id", "zona_id", name="uq_tamano_zona_id_zona"),
        sa.CheckConstraint(
            "btrim(etiqueta) <> ''", name="ck_tamano_zona_etiqueta"
        ),
        sa.CheckConstraint(
            (
                "ancho_mm > 0 AND ancho_mm < 'Infinity'::numeric "
                "AND alto_mm > 0 AND alto_mm < "
                "'Infinity'::numeric"
            ),
            name="ck_tamano_zona_dimensiones",
        ),
        sa.CheckConstraint(
            "recargo_centavos >= 0", name="ck_tamano_zona_recargo"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tamano_zona"),
    )

    id: Mapped[UUID] = mapped_column(
        "id", sa.Uuid, nullable=False, primary_key=True, default=uuid4
    )
    zone_id: Mapped[UUID] = mapped_column("zona_id", sa.Uuid, nullable=False)
    label: Mapped[str] = mapped_column("etiqueta", sa.Text, nullable=False)
    width_mm: Mapped[Decimal] = mapped_column(
        "ancho_mm", sa.Numeric(), nullable=False
    )
    height_mm: Mapped[Decimal] = mapped_column(
        "alto_mm", sa.Numeric(), nullable=False
    )
    surcharge_cents: Mapped[int] = mapped_column(
        "recargo_centavos", sa.BigInteger, nullable=False
    )
