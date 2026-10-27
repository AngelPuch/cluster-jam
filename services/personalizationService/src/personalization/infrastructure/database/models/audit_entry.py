"""Map auditoria_local using explicit Spanish SQL identifiers."""

from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AuditEntryModel(Base):
    """Persist auditoria_local inside the service database."""

    __tablename__ = "auditoria_local"
    __table_args__ = (
        sa.CheckConstraint(
            "btrim(accion) <> '' AND btrim(recurso) <> ''",
            name="ck_auditoria_local_textos",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_auditoria_local"),
        sa.Index(
            "ix_auditoria_local_recurso", "recurso", "recurso_id", "creado_en"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        "id", sa.Uuid, nullable=False, primary_key=True, default=uuid4
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        "actor_ref", sa.Uuid, nullable=True
    )
    action: Mapped[str] = mapped_column("accion", sa.Text, nullable=False)
    resource: Mapped[str] = mapped_column("recurso", sa.Text, nullable=False)
    resource_id: Mapped[UUID] = mapped_column(
        "recurso_id", sa.Uuid, nullable=False
    )
    detail: Mapped[dict[str, object] | None] = mapped_column(
        "detalle", postgresql.JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        "creado_en",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )
