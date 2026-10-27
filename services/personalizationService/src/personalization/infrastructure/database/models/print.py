"""Map estampado using explicit Spanish SQL identifiers."""

from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PrintModel(Base):
    """Persist estampado inside the service database."""

    __tablename__ = "estampado"
    __table_args__ = (
        sa.CheckConstraint("btrim(nombre) <> ''", name="ck_estampado_nombre"),
        sa.PrimaryKeyConstraint("id", name="pk_estampado"),
    )

    id: Mapped[UUID] = mapped_column(
        "id", sa.Uuid, nullable=False, primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column("nombre", sa.String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(
        "descripcion", sa.Text, nullable=True
    )
    active: Mapped[bool] = mapped_column("activo", sa.Boolean, nullable=False)
