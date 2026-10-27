"""Create personalization tables from database model v1.1.

Revision ID: 0001_personalization
Revises: None
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_personalization"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create only tables owned by Personalization Service."""
    op.create_table(
        "archivo",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("propietario_ref", sa.Uuid, nullable=False),
        sa.Column("bucket", sa.Text, nullable=False),
        sa.Column("objeto_clave", sa.Text, nullable=False),
        sa.Column("sha256", sa.CHAR(64), nullable=False),
        sa.Column("mime", sa.Text, nullable=False),
        sa.Column("bytes", sa.BigInteger, nullable=False),
        sa.Column("ancho_px", sa.Integer, nullable=False),
        sa.Column("alto_px", sa.Integer, nullable=False),
        sa.Column("uso", sa.Text, nullable=False),
        sa.Column("estado", sa.Text, nullable=False),
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
        schema="app",
    )
    op.create_index(
        "ix_archivo_propietario",
        "archivo",
        ["propietario_ref", "id"],
        schema="app",
    )
    op.create_table(
        "estampado",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("descripcion", sa.Text, nullable=True),
        sa.Column("activo", sa.Boolean, nullable=False),
        sa.CheckConstraint("btrim(nombre) <> ''", name="ck_estampado_nombre"),
        sa.PrimaryKeyConstraint("id", name="pk_estampado"),
        schema="app",
    )
    op.create_table(
        "estampado_version",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("estampado_id", sa.Uuid, nullable=False),
        sa.Column("numero", sa.Integer, nullable=False),
        sa.Column("archivo_id", sa.Uuid, nullable=False),
        sa.Column("recargo_centavos", sa.BigInteger, nullable=False),
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
        schema="app",
    )
    op.create_index(
        "ix_estampado_version_archivo",
        "estampado_version",
        ["archivo_id"],
        schema="app",
    )
    op.create_table(
        "plantilla_version",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("producto_ref", sa.Uuid, nullable=False),
        sa.Column("talla_ref", sa.SmallInteger, nullable=False),
        sa.Column("numero", sa.Integer, nullable=False),
        sa.Column("ancho_frente_mm", sa.Numeric(), nullable=False),
        sa.Column("alto_frente_mm", sa.Numeric(), nullable=False),
        sa.Column("ancho_espalda_mm", sa.Numeric(), nullable=False),
        sa.Column("alto_espalda_mm", sa.Numeric(), nullable=False),
        sa.Column("activa", sa.Boolean, nullable=False),
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
        schema="app",
    )
    op.create_table(
        "zona",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("plantilla_id", sa.Uuid, nullable=False),
        sa.Column("codigo", sa.String(40), nullable=False),
        sa.Column("cara", sa.Text, nullable=False),
        sa.Column("x_mm", sa.Numeric(), nullable=False),
        sa.Column("y_mm", sa.Numeric(), nullable=False),
        sa.Column("ancho_mm", sa.Numeric(), nullable=False),
        sa.Column("alto_mm", sa.Numeric(), nullable=False),
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
        schema="app",
    )
    op.create_table(
        "tamano_zona",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("zona_id", sa.Uuid, nullable=False),
        sa.Column("etiqueta", sa.Text, nullable=False),
        sa.Column("ancho_mm", sa.Numeric(), nullable=False),
        sa.Column("alto_mm", sa.Numeric(), nullable=False),
        sa.Column("recargo_centavos", sa.BigInteger, nullable=False),
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
        schema="app",
    )
    op.create_table(
        "diseno",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("usuario_ref", sa.Uuid, nullable=False),
        sa.Column("variante_ref", sa.Uuid, nullable=False),
        sa.Column("plantilla_id", sa.Uuid, nullable=False),
        sa.Column("estado", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("previa_frente_id", sa.Uuid, nullable=True),
        sa.Column("previa_espalda_id", sa.Uuid, nullable=True),
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
        schema="app",
    )
    op.create_index(
        "ix_diseno_usuario", "diseno", ["usuario_ref", "id"], schema="app"
    )
    op.create_index(
        "ix_diseno_plantilla", "diseno", ["plantilla_id"], schema="app"
    )
    op.create_index(
        "ix_diseno_previa_frente", "diseno", ["previa_frente_id"], schema="app"
    )
    op.create_index(
        "ix_diseno_previa_espalda",
        "diseno",
        ["previa_espalda_id"],
        schema="app",
    )
    op.create_table(
        "aplicacion",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("diseno_id", sa.Uuid, nullable=False),
        sa.Column("zona_id", sa.Uuid, nullable=False),
        sa.Column("tamano_id", sa.Uuid, nullable=False),
        sa.Column("estampado_version_id", sa.Uuid, nullable=True),
        sa.Column("archivo_usuario_id", sa.Uuid, nullable=True),
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
        schema="app",
    )
    op.create_index(
        "ix_aplicacion_zona", "aplicacion", ["zona_id"], schema="app"
    )
    op.create_index(
        "ix_aplicacion_tamano_zona",
        "aplicacion",
        ["tamano_id", "zona_id"],
        schema="app",
    )
    op.create_index(
        "ix_aplicacion_estampado",
        "aplicacion",
        ["estampado_version_id"],
        schema="app",
    )
    op.create_index(
        "ix_aplicacion_archivo",
        "aplicacion",
        ["archivo_usuario_id"],
        schema="app",
    )
    op.create_table(
        "auditoria_local",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("actor_ref", sa.Uuid, nullable=True),
        sa.Column("accion", sa.Text, nullable=False),
        sa.Column("recurso", sa.Text, nullable=False),
        sa.Column("recurso_id", sa.Uuid, nullable=False),
        sa.Column("detalle", postgresql.JSONB, nullable=True),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "btrim(accion) <> '' AND btrim(recurso) <> ''",
            name="ck_auditoria_local_textos",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_auditoria_local"),
        schema="app",
    )
    op.create_index(
        "ix_auditoria_local_recurso",
        "auditoria_local",
        ["recurso", "recurso_id", "creado_en"],
        schema="app",
    )


def downgrade() -> None:
    """Remove domain tables in reverse dependency order."""
    op.drop_table("auditoria_local", schema="app")
    op.drop_table("aplicacion", schema="app")
    op.drop_table("diseno", schema="app")
    op.drop_table("tamano_zona", schema="app")
    op.drop_table("zona", schema="app")
    op.drop_table("plantilla_version", schema="app")
    op.drop_table("estampado_version", schema="app")
    op.drop_table("estampado", schema="app")
    op.drop_table("archivo", schema="app")
