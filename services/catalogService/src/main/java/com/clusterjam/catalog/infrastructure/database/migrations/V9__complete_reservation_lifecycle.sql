ALTER TABLE app.reserva
    ADD COLUMN payment_id UUID,
    ADD COLUMN ultimo_evento_id UUID,
    ADD CONSTRAINT fk_reserva_ultimo_evento FOREIGN KEY (ultimo_evento_id)
        REFERENCES app.outbox_catalogo(id) DEFERRABLE INITIALLY DEFERRED,
    ADD CONSTRAINT ck_reserva_pago_confirmado
        CHECK (estado NOT IN ('CONFIRMADA', 'CONSUMIDA') OR payment_id IS NOT NULL);

GRANT UPDATE (estado, payment_id, ultimo_evento_id) ON app.reserva TO app_catalogo;
GRANT UPDATE (stock_fisico, stock_reservado, version, actualizado_en) ON app.inventario TO app_catalogo;
