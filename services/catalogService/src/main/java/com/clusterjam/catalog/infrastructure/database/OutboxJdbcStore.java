package com.clusterjam.catalog.infrastructure.database;

import java.util.Optional;
import java.util.UUID;

import com.clusterjam.catalog.application.outbox.OutboxEvent;
import com.clusterjam.catalog.application.ports.OutboxStore;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.stereotype.Repository;

@Repository
public class OutboxJdbcStore implements OutboxStore {

    private final JdbcOperations jdbc;

    public OutboxJdbcStore(JdbcOperations jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public Optional<OutboxEvent> nextPending() {
        return jdbc.query("""
            SELECT id, exchange, routing_key, cuerpo::text AS body, cuerpo->>'orderId' AS order_id
            FROM app.outbox_catalogo WHERE estado = 'PENDING'
            ORDER BY creado_en, id LIMIT 1 FOR NO KEY UPDATE SKIP LOCKED
            """, (row, index) -> new OutboxEvent(row.getObject("id", UUID.class),
                UUID.fromString(row.getString("order_id")), row.getString("exchange"),
                row.getString("routing_key"), row.getString("body"))).stream().findFirst();
    }

    @Override
    public void markPublished(UUID messageId) {
        int changed = jdbc.update("""
            UPDATE app.outbox_catalogo SET estado = 'PUBLISHED', publicado_en = clock_timestamp()
            WHERE id = ? AND estado = 'PENDING'
            """, messageId);
        if (changed != 1) {
            throw new IllegalStateException("Outbox row changed unexpectedly");
        }
    }
}
