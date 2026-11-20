CREATE TABLE app.foto_limpieza (
    id UUID PRIMARY KEY,
    bucket TEXT NOT NULL,
    objeto_clave TEXT NOT NULL,
    miniatura_objeto_clave TEXT NOT NULL,
    limpiar_despues TIMESTAMPTZ NOT NULL,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_foto_limpieza_fecha ON app.foto_limpieza (limpiar_despues);

GRANT SELECT, INSERT, DELETE ON app.foto_limpieza TO app_catalogo;
-- PostgreSQL requires UPDATE privilege for SELECT FOR UPDATE on the task row.
GRANT UPDATE (limpiar_despues) ON app.foto_limpieza TO app_catalogo;
GRANT SELECT, INSERT ON app.foto_producto TO app_catalogo;
GRANT UPDATE (bucket, objeto_clave, miniatura_objeto_clave, activo, version, actualizado_en)
    ON app.foto_producto TO app_catalogo;
