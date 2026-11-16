CREATE TABLE app.auditoria_local (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_ref UUID NOT NULL,
    accion VARCHAR(40) NOT NULL CHECK (btrim(accion) <> ''),
    recurso VARCHAR(40) NOT NULL CHECK (btrim(recurso) <> ''),
    recurso_id UUID NOT NULL,
    detalle JSONB NOT NULL CHECK (jsonb_typeof(detalle) = 'object'),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_auditoria_recurso ON app.auditoria_local (recurso, recurso_id, creado_en);
CREATE INDEX ix_variante_producto_id ON app.variante (producto_id, id);

GRANT SELECT ON app.producto, app.variante TO app_catalogo;
GRANT SELECT (id) ON app.tipo_prenda, app.talla, app.color TO app_catalogo;

GRANT INSERT (tipo_prenda_id, nombre, descripcion),
    UPDATE (tipo_prenda_id, nombre, descripcion, estado, version, actualizado_en)
    ON app.producto TO app_catalogo;

GRANT INSERT (producto_id, talla_id, color_id, sku, precio_base_centavos),
    UPDATE (precio_base_centavos, estado, version, actualizado_en)
    ON app.variante TO app_catalogo;

GRANT INSERT (variante_id) ON app.inventario TO app_catalogo;
GRANT INSERT (actor_ref, accion, recurso, recurso_id, detalle) ON app.auditoria_local TO app_catalogo;
