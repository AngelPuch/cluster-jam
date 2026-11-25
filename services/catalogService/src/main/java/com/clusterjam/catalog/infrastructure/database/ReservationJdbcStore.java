package com.clusterjam.catalog.infrastructure.database;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.UUID;

import com.clusterjam.catalog.application.ports.ReservationStore;
import com.clusterjam.catalog.application.reservations.ReservationMessages;
import com.clusterjam.catalog.application.reservations.ReservationMessages.CreatedData;
import com.clusterjam.catalog.application.reservations.ReservationMessages.RejectedData;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ReserveCommand;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ReserveLine;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ResultMessage;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.json.JsonMapper;

@Repository
public class ReservationJdbcStore implements ReservationStore {

    private final JdbcOperations jdbc;
    private final JsonMapper json;

    public ReservationJdbcStore(JdbcOperations jdbc, JsonMapper json) {
        this.jdbc = jdbc;
        this.json = json;
    }

    @Override
    public void reserve(ReserveCommand command) {
        UUID resultId = UUID.randomUUID();
        int claimed = jdbc.update("""
            INSERT INTO app.inbox_catalogo(consumidor, message_id, order_id, resultado_id)
            VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING
            """, ReservationMessages.RESERVE, command.messageId(), command.orderId(), resultId);
        if (claimed == 0) {
            return;
        }

        List<ReserveLine> lines = command.data().lines().stream()
            .sorted(Comparator.comparing(line -> line.variantId().toString())).toList();
        List<Stock> stocks = lockStocks(lines);
        Instant now = jdbc.queryForObject("SELECT clock_timestamp()",
            (row, index) -> row.getTimestamp(1).toInstant());
        String reason = rejection(command, lines, stocks, now);
        if (reason != null) {
            result(command, resultId, ReservationMessages.REJECTED, now, new RejectedData(reason));
            return;
        }

        UUID reservationId = UUID.randomUUID();
        Instant expiresAt = now.plusSeconds(900);
        jdbc.update("""
            INSERT INTO app.reserva(id, order_id, creado_en, expira_en) VALUES (?, ?, ?, ?)
            """, reservationId, command.orderId(), Timestamp.from(now), Timestamp.from(expiresAt));
        for (ReserveLine line : lines) {
            int changed = jdbc.update("""
                UPDATE app.inventario SET stock_reservado = stock_reservado + ?,
                    version = version + 1, actualizado_en = clock_timestamp()
                WHERE variante_id = ? AND stock_fisico - stock_reservado >= ? AND version < 2147483647
                """, line.quantity(), line.variantId(), line.quantity());
            if (changed != 1) {
                throw new IllegalStateException("Inventory update failed");
            }
            jdbc.update("""
                INSERT INTO app.detalle_reserva(reserva_id, variante_id, cantidad, precio_base_centavos)
                VALUES (?, ?, ?, ?)
                """, reservationId, line.variantId(), line.quantity(), line.expectedBasePriceCents());
        }
        result(command, resultId, ReservationMessages.CREATED, now, new CreatedData(reservationId, expiresAt));
    }

    private List<Stock> lockStocks(List<ReserveLine> lines) {
        var products = new ArrayList<UUID>();
        for (ReserveLine line : lines) {
            products.addAll(jdbc.query("SELECT producto_id FROM app.variante WHERE id = ?",
                (row, index) -> row.getObject(1, UUID.class), line.variantId()));
        }
        // producto_id cannot be changed by the API/application role.
        for (UUID productId : products.stream().distinct().sorted(Comparator.comparing(UUID::toString)).toList()) {
            jdbc.query("SELECT id FROM app.producto WHERE id = ? FOR SHARE",
                (row, index) -> row.getObject(1, UUID.class), productId);
        }
        for (ReserveLine line : lines) {
            jdbc.query("SELECT id FROM app.variante WHERE id = ? FOR SHARE",
                (row, index) -> row.getObject(1, UUID.class), line.variantId());
        }

        var stocks = new ArrayList<Stock>();
        for (ReserveLine line : lines) {
            stocks.addAll(jdbc.query("""
                SELECT i.stock_fisico, i.stock_reservado, v.precio_base_centavos,
                    v.estado AS variante_estado, p.estado AS producto_estado
                FROM app.inventario i JOIN app.variante v ON v.id = i.variante_id
                JOIN app.producto p ON p.id = v.producto_id
                WHERE i.variante_id = ? FOR UPDATE OF i
                """, (row, index) -> new Stock(row.getInt("stock_fisico"), row.getInt("stock_reservado"),
                    row.getLong("precio_base_centavos"), row.getString("variante_estado"),
                    row.getString("producto_estado")), line.variantId()));
        }
        return stocks;
    }

    private String rejection(ReserveCommand command, List<ReserveLine> lines, List<Stock> stocks, Instant now) {
        if (!now.isBefore(command.data().quoteValidUntil())) {
            return "QUOTE_EXPIRED";
        }
        if (stocks.size() != lines.size() || stocks.stream().anyMatch(stock ->
            !stock.variantState().equals("PUBLICADO") || !stock.productState().equals("PUBLICADO"))) {
            return "VARIANT_UNAVAILABLE";
        }
        for (int index = 0; index < lines.size(); index++) {
            if (stocks.get(index).price() != lines.get(index).expectedBasePriceCents()) {
                return "PRICE_CHANGED";
            }
        }
        for (int index = 0; index < lines.size(); index++) {
            Stock stock = stocks.get(index);
            if (stock.physical() - stock.reserved() < lines.get(index).quantity()) {
                return "OUT_OF_STOCK";
            }
        }
        return null;
    }

    private void result(ReserveCommand command, UUID id, String type, Instant now, Object data) {
        var message = new ResultMessage(id, type, command.orderId(), now, data);
        jdbc.update("""
            INSERT INTO app.outbox_catalogo(id, exchange, routing_key, cuerpo)
            VALUES (?, 'catalog.events', ?, CAST(? AS jsonb))
            """, id, type, json.writeValueAsString(message));
    }

    private record Stock(int physical, int reserved, long price, String variantState, String productState) {
    }
}
