CREATE TABLE app.movimiento_inventario (
    id UUID PRIMARY KEY,
    variante_id UUID NOT NULL REFERENCES app.inventario (variante_id),
    tipo VARCHAR(16) NOT NULL CHECK (tipo = 'AJUSTE'),
    cantidad_delta INTEGER NOT NULL CHECK (cantidad_delta BETWEEN -1000000 AND 1000000 AND cantidad_delta <> 0),
    motivo VARCHAR(200) NOT NULL CHECK (btrim(motivo) <> '' AND motivo !~ '[[:cntrl:]]'),
    actor_ref UUID NOT NULL,
    fisico_antes INTEGER NOT NULL CHECK (fisico_antes >= 0),
    fisico_despues INTEGER NOT NULL,
    reservado INTEGER NOT NULL CHECK (reservado >= 0),
    version_despues INTEGER NOT NULL CHECK (version_despues > 0),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_movimiento_saldos CHECK (
        fisico_antes >= reservado AND fisico_despues >= reservado
        AND fisico_despues::bigint = fisico_antes::bigint + cantidad_delta::bigint
    ),
    CONSTRAINT uq_movimiento_variante_version UNIQUE (variante_id, version_despues)
);

CREATE TABLE app.idempotencia_ajuste (
    actor_ref UUID NOT NULL,
    operacion VARCHAR(40) NOT NULL CHECK (operacion = 'ADJUST_INVENTORY_V1'),
    clave UUID NOT NULL,
    solicitud_hash CHAR(64) NOT NULL CHECK (solicitud_hash ~ '^[0-9a-f]{64}$'),
    movimiento_id UUID NOT NULL UNIQUE,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (actor_ref, operacion, clave),
    CONSTRAINT fk_idempotencia_movimiento FOREIGN KEY (movimiento_id)
        REFERENCES app.movimiento_inventario (id) DEFERRABLE INITIALLY DEFERRED
);

GRANT SELECT, INSERT ON app.movimiento_inventario, app.idempotencia_ajuste TO app_catalogo;
GRANT SELECT (version) ON app.inventario TO app_catalogo;
GRANT UPDATE (stock_fisico, version, actualizado_en) ON app.inventario TO app_catalogo;
