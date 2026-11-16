CREATE TABLE app.tipo_prenda (
    id SMALLINT PRIMARY KEY CHECK (id > 0),
    nombre VARCHAR(40) NOT NULL UNIQUE CHECK (btrim(nombre) <> '')
);

CREATE TABLE app.talla (
    id SMALLINT PRIMARY KEY CHECK (id > 0),
    codigo VARCHAR(12) NOT NULL UNIQUE CHECK (btrim(codigo) <> ''),
    orden SMALLINT NOT NULL UNIQUE CHECK (orden > 0)
);

CREATE TABLE app.color (
    id SMALLINT PRIMARY KEY CHECK (id > 0),
    nombre VARCHAR(40) NOT NULL UNIQUE CHECK (btrim(nombre) <> ''),
    codigo_hex CHAR(7) NOT NULL CHECK (codigo_hex ~ '^#[0-9A-F]{6}$')
);

CREATE TABLE app.producto (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tipo_prenda_id SMALLINT NOT NULL REFERENCES app.tipo_prenda (id),
    nombre VARCHAR(120) NOT NULL CHECK (btrim(nombre) <> ''),
    descripcion TEXT,
    estado TEXT NOT NULL DEFAULT 'BORRADOR',
    version INTEGER NOT NULL DEFAULT 0 CHECK (version >= 0),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_producto_estado CHECK (estado IN ('BORRADOR', 'PUBLICADO', 'RETIRADO'))
);

CREATE TABLE app.variante (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    producto_id UUID NOT NULL REFERENCES app.producto (id),
    talla_id SMALLINT NOT NULL REFERENCES app.talla (id),
    color_id SMALLINT NOT NULL REFERENCES app.color (id),
    sku VARCHAR(60) NOT NULL,
    precio_base_centavos BIGINT NOT NULL CHECK (precio_base_centavos >= 0),
    estado TEXT NOT NULL DEFAULT 'BORRADOR',
    version INTEGER NOT NULL DEFAULT 0 CHECK (version >= 0),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_variante_sku UNIQUE (sku),
    CONSTRAINT uq_variante_producto_talla_color UNIQUE (producto_id, talla_id, color_id),
    CONSTRAINT ck_variante_sku CHECK (sku ~ '^[A-Z0-9][A-Z0-9_.-]{0,59}$'),
    CONSTRAINT ck_variante_estado CHECK (estado IN ('BORRADOR', 'PUBLICADO', 'RETIRADO'))
);

CREATE TABLE app.foto_producto (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    producto_id UUID NOT NULL REFERENCES app.producto (id),
    color_id SMALLINT NOT NULL REFERENCES app.color (id),
    cara TEXT NOT NULL CHECK (cara IN ('FRENTE', 'ESPALDA')),
    bucket TEXT NOT NULL CHECK (btrim(bucket) <> ''),
    objeto_clave TEXT NOT NULL CHECK (btrim(objeto_clave) <> ''),
    miniatura_objeto_clave TEXT NOT NULL CHECK (btrim(miniatura_objeto_clave) <> ''),
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    version INTEGER NOT NULL DEFAULT 0 CHECK (version >= 0),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_foto_producto_color_cara UNIQUE (producto_id, color_id, cara),
    CONSTRAINT ck_foto_claves_distintas CHECK (objeto_clave <> miniatura_objeto_clave)
);

CREATE TABLE app.inventario (
    variante_id UUID PRIMARY KEY REFERENCES app.variante (id),
    stock_fisico INTEGER NOT NULL DEFAULT 0,
    stock_reservado INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 0 CHECK (version >= 0),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_inventario_stock CHECK (stock_reservado >= 0 AND stock_fisico >= stock_reservado)
);

CREATE INDEX ix_producto_tipo ON app.producto (tipo_prenda_id);
CREATE INDEX ix_producto_publicado_nombre
    ON app.producto (lower(nombre), id) WHERE estado = 'PUBLICADO';
CREATE INDEX ix_variante_talla ON app.variante (talla_id);
CREATE INDEX ix_variante_color ON app.variante (color_id);
CREATE INDEX ix_variante_publicada_precio
    ON app.variante (producto_id, precio_base_centavos, id) WHERE estado = 'PUBLICADO';
CREATE INDEX ix_foto_producto_color ON app.foto_producto (color_id);

GRANT SELECT (installed_rank, version, type, script, success)
    ON app.flyway_schema_history TO app_catalogo;
