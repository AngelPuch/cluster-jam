"""Map plantilla_version using explicit Spanish SQL identifiers."""

from decimal import Decimal
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class TemplateVersionModel(Base):
    """Persist plantilla_version inside the service database."""

    __tablename__ = "plantilla_version"
    __table_args__ = (
        sa.UniqueConstraint(
            "producto_ref",
            "talla_ref",
            "numero",
            name="uq_plantilla_version_numero",
        ),
        sa.CheckConstraint("numero > 0", name="ck_plantilla_version_numero"),
        sa.CheckConstraint(
            (
                "ancho_frente_mm > 0 AND ancho_frente_mm < "
                "'Infinity'::numeric AND alto_frente_mm > 0 AND "
                "alto_frente_mm < 'Infinity'::numeric AND "
                "ancho_espalda_mm > 0 AND ancho_espalda_mm < "
                "'Infinity'::numeric AND alto_espalda_mm > 0 AND "
                "alto_espalda_mm < 'Infinity'::numeric"
            ),
            name="ck_plantilla_version_dimensiones",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_plantilla_version"),
    )

    id: Mapped[UUID] = mapped_column(
        "id", sa.Uuid, nullable=False, primary_key=True, default=uuid4
    )
    product_id: Mapped[UUID] = mapped_column(
        "producto_ref", sa.Uuid, nullable=False
    )
    size_id: Mapped[int] = mapped_column(
        "talla_ref", sa.SmallInteger, nullable=False
    )
    number: Mapped[int] = mapped_column("numero", sa.Integer, nullable=False)
    front_width_mm: Mapped[Decimal] = mapped_column(
        "ancho_frente_mm", sa.Numeric(), nullable=False
    )
    front_height_mm: Mapped[Decimal] = mapped_column(
        "alto_frente_mm", sa.Numeric(), nullable=False
    )
    back_width_mm: Mapped[Decimal] = mapped_column(
        "ancho_espalda_mm", sa.Numeric(), nullable=False
    )
    back_height_mm: Mapped[Decimal] = mapped_column(
        "alto_espalda_mm", sa.Numeric(), nullable=False
    )
    active: Mapped[bool] = mapped_column("activa", sa.Boolean, nullable=False)
