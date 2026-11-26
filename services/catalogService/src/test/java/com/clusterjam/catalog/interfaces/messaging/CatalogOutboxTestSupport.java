package com.clusterjam.catalog.interfaces.messaging;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.sql.Connection;
import java.sql.SQLException;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;

import com.clusterjam.catalog.application.outbox.OutboxEvent;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ResultMessage;
import org.springframework.jdbc.core.JdbcOperations;
import tools.jackson.databind.json.JsonMapper;

final class CatalogOutboxTestSupport {

    private CatalogOutboxTestSupport() {
    }

    static Connection lockExistingPending() throws SQLException {
        Connection holder = ReservationStockTest.admin().getDataSource().getConnection();
        holder.setAutoCommit(false);
        try (var statement = holder.prepareStatement("""
            SELECT id FROM app.outbox_catalogo WHERE estado = 'PENDING' FOR UPDATE
            """); var rows = statement.executeQuery()) {
            while (rows.next()) {
                rows.getObject(1);
            }
        } catch (SQLException failure) {
            holder.close();
            throw failure;
        }
        return holder;
    }

    static OutboxEvent insert(String type) {
        UUID id = UUID.randomUUID();
        UUID order = UUID.randomUUID();
        String body = new JsonMapper().writeValueAsString(
            new ResultMessage(id, type, order, Instant.now(), Map.of("reason", "OUT_OF_STOCK")));
        ReservationStockTest.admin().update("""
            INSERT INTO app.outbox_catalogo(id, exchange, routing_key, cuerpo)
            VALUES (?, 'catalog.events', ?, CAST(? AS jsonb))
            """, id, type, body);
        return new OutboxEvent(id, order, "catalog.events", type, body);
    }

    static void assertState(JdbcOperations jdbc, UUID id, String expected) {
        jdbc.queryForObject("SELECT estado, publicado_en FROM app.outbox_catalogo WHERE id = ?", (row, index) -> {
            assertEquals(expected, row.getString("estado"));
            if (expected.equals("PENDING")) {
                assertNull(row.getTimestamp("publicado_en"));
            } else {
                assertNotNull(row.getTimestamp("publicado_en"));
            }
            return true;
        }, id);
    }

    static void remove(UUID id) {
        ReservationStockTest.admin().update("DELETE FROM app.outbox_catalogo WHERE id = ?", id);
    }
}
