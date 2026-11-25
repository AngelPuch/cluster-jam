CREATE TABLE app.outbox_catalogo (
    id UUID PRIMARY KEY,
    exchange VARCHAR(80) NOT NULL,
    routing_key VARCHAR(120) NOT NULL,
    cuerpo JSONB NOT NULL CHECK (jsonb_typeof(cuerpo) = 'object'),
    estado VARCHAR(16) NOT NULL DEFAULT 'PENDING' CHECK (estado IN ('PENDING', 'PUBLISHED')),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    publicado_en TIMESTAMPTZ
);

CREATE INDEX ix_outbox_catalogo_pendiente ON app.outbox_catalogo (creado_en, id)
    WHERE estado = 'PENDING';

CREATE TABLE app.inbox_catalogo (
    consumidor VARCHAR(100) NOT NULL,
    message_id UUID NOT NULL,
    order_id UUID NOT NULL,
    resultado_id UUID NOT NULL,
    procesado_en TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (consumidor, message_id),
    CONSTRAINT uq_inbox_catalogo_operacion_pedido UNIQUE (consumidor, order_id),
    CONSTRAINT fk_inbox_catalogo_resultado FOREIGN KEY (resultado_id)
        REFERENCES app.outbox_catalogo (id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE app.reserva (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL UNIQUE,
    estado VARCHAR(16) NOT NULL DEFAULT 'ACTIVA'
        CHECK (estado IN ('ACTIVA', 'CONFIRMADA', 'LIBERADA', 'EXPIRADA', 'CONSUMIDA')),
    creado_en TIMESTAMPTZ NOT NULL,
    expira_en TIMESTAMPTZ NOT NULL,
    CHECK (expira_en > creado_en)
);

CREATE INDEX ix_reserva_activa_expiracion ON app.reserva (expira_en, id) WHERE estado = 'ACTIVA';

CREATE TABLE app.detalle_reserva (
    reserva_id UUID NOT NULL REFERENCES app.reserva (id),
    variante_id UUID NOT NULL REFERENCES app.inventario (variante_id),
    cantidad INTEGER NOT NULL CHECK (cantidad > 0),
    precio_base_centavos BIGINT NOT NULL CHECK (precio_base_centavos BETWEEN 1 AND 10000000),
    PRIMARY KEY (reserva_id, variante_id)
);

GRANT SELECT, INSERT ON app.outbox_catalogo, app.inbox_catalogo, app.reserva, app.detalle_reserva TO app_catalogo;
GRANT UPDATE (stock_reservado, version, actualizado_en) ON app.inventario TO app_catalogo;
