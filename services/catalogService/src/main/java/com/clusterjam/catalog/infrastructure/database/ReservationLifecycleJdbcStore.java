package com.clusterjam.catalog.infrastructure.database;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import com.clusterjam.catalog.application.ports.ReservationLifecycleStore;
import com.clusterjam.catalog.application.reservations.InvalidReservationMessage;
import com.clusterjam.catalog.application.reservations.ReservationMessages;
import com.clusterjam.catalog.application.reservations.ReservationMessages.Command;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ConfirmCommand;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ConfirmedData;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ConsumeCommand;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ConsumedData;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ExpiredData;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ReleaseCommand;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ReleasedData;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ResultMessage;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.json.JsonMapper;

@Repository
public class ReservationLifecycleJdbcStore implements ReservationLifecycleStore {

    private static final String RESERVATIONS = """
        SELECT id, order_id, estado, expira_en, payment_id, ultimo_evento_id FROM app.reserva
        """;
    private final JdbcOperations jdbc;
    private final JsonMapper json;

    public ReservationLifecycleJdbcStore(JdbcOperations jdbc, JsonMapper json) {
        this.jdbc = jdbc;
        this.json = json;
    }

    @Override
    public void transition(Command command) {
        UUID reservationId = switch (command) {
            case ConfirmCommand confirm -> confirm.data().reservationId();
            case ReleaseCommand release -> release.data().reservationId();
            case ConsumeCommand consume -> consume.data().reservationId();
            default -> throw new InvalidReservationMessage();
        };
        if (Boolean.TRUE.equals(jdbc.queryForObject("""
            SELECT EXISTS(SELECT 1 FROM app.inbox_catalogo WHERE consumidor = ? AND message_id = ?)
            """, Boolean.class, command.type(), command.messageId()))) {
            return;
        }
        List<Reservation> found = jdbc.query(RESERVATIONS + " WHERE id = ? AND order_id = ? FOR UPDATE",
            (row, index) -> reservation(row), reservationId, command.orderId());
        if (found.isEmpty()) {
            throw new InvalidReservationMessage();
        }
        Reservation reservation = found.getFirst();
        if (command instanceof ConfirmCommand confirm && reservation.paymentId() != null
            && !reservation.paymentId().equals(confirm.data().paymentId())) {
            throw new InvalidReservationMessage();
        }

        boolean changes = command instanceof ConfirmCommand && reservation.state().equals("ACTIVA")
            || command instanceof ReleaseCommand
                && List.of("ACTIVA", "CONFIRMADA").contains(reservation.state())
            || command instanceof ConsumeCommand && reservation.state().equals("CONFIRMADA");
        UUID resultId = changes ? UUID.randomUUID() : reservation.lastEvent();
        if (resultId == null) {
            throw new InvalidReservationMessage();
        }
        int claimed = jdbc.update("""
            INSERT INTO app.inbox_catalogo(consumidor, message_id, order_id, resultado_id)
            VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING
            """, command.type(), command.messageId(), command.orderId(), resultId);
        if (claimed == 0) {
            return;
        }

        switch (command) {
            case ConfirmCommand confirm -> confirm(reservation, resultId, confirm);
            case ReleaseCommand release -> release(reservation, resultId, release);
            case ConsumeCommand consume -> consume(reservation, resultId);
            default -> throw new InvalidReservationMessage();
        }
    }

    @Override
    public boolean expireNext() {
        List<Reservation> found = jdbc.query(RESERVATIONS + """
             WHERE estado = 'ACTIVA' AND expira_en <= clock_timestamp()
             ORDER BY expira_en, id LIMIT 1 FOR UPDATE SKIP LOCKED
            """, (row, index) -> reservation(row));
        if (found.isEmpty()) {
            return false;
        }
        finish(found.getFirst(), UUID.randomUUID(), "EXPIRADA", null);
        return true;
    }

    private void confirm(Reservation reservation, UUID resultId, ConfirmCommand command) {
        if (reservation.state().equals("ACTIVA")) {
            Instant now = now();
            int changed = jdbc.update("""
                UPDATE app.reserva SET estado = 'CONFIRMADA', payment_id = ?, ultimo_evento_id = ?
                WHERE id = ? AND estado = 'ACTIVA' AND expira_en > clock_timestamp()
                """, command.data().paymentId(), resultId, reservation.id());
            if (changed == 1) {
                result(reservation, resultId, ReservationMessages.CONFIRMED, now,
                    new ConfirmedData(reservation.id(), command.data().paymentId()));
            } else {
                finish(reservation, resultId, "EXPIRADA", null);
            }
        } else if (!List.of("CONFIRMADA", "LIBERADA", "EXPIRADA").contains(reservation.state())) {
            throw new InvalidReservationMessage();
        }
        // A terminal no-op links inbox to the existing event; it does not invent a new fact.
    }

    private void release(Reservation reservation, UUID resultId, ReleaseCommand command) {
        if (List.of("ACTIVA", "CONFIRMADA").contains(reservation.state())) {
            finish(reservation, resultId, "LIBERADA", command.data().reason());
        } else if (!List.of("LIBERADA", "EXPIRADA").contains(reservation.state())) {
            throw new InvalidReservationMessage();
        }
    }

    private void consume(Reservation reservation, UUID resultId) {
        if (reservation.state().equals("CONFIRMADA")) {
            finish(reservation, resultId, "CONSUMIDA", null);
        } else if (!reservation.state().equals("CONSUMIDA")) {
            throw new InvalidReservationMessage();
        }
    }

    private void finish(Reservation reservation, UUID eventId, String state, String reason) {
        List<Line> lines = jdbc.query("""
            SELECT d.variante_id, d.cantidad FROM app.detalle_reserva d
            JOIN app.inventario i ON i.variante_id = d.variante_id
            WHERE d.reserva_id = ? ORDER BY d.variante_id FOR UPDATE OF i
            """, (row, index) -> new Line(row.getObject("variante_id", UUID.class), row.getInt("cantidad")),
            reservation.id());
        if (lines.isEmpty()) {
            throw new IllegalStateException("Reservation has no inventory lines");
        }
        Instant now = now();
        if (state.equals("EXPIRADA") && now.isBefore(reservation.expiresAt())) {
            throw new IllegalStateException("Reservation is not expired");
        }
        for (Line line : lines) {
            int changed;
            if (state.equals("CONSUMIDA")) {
                changed = jdbc.update("""
                    UPDATE app.inventario SET stock_fisico = stock_fisico - ?,
                        stock_reservado = stock_reservado - ?, version = version + 1,
                        actualizado_en = clock_timestamp()
                    WHERE variante_id = ? AND stock_reservado >= ? AND stock_fisico >= ?
                        AND version < 2147483647
                    """, line.quantity(), line.quantity(), line.variantId(), line.quantity(), line.quantity());
            } else {
                changed = jdbc.update("""
                    UPDATE app.inventario SET stock_reservado = stock_reservado - ?,
                        version = version + 1, actualizado_en = clock_timestamp()
                    WHERE variante_id = ? AND stock_reservado >= ? AND version < 2147483647
                    """, line.quantity(), line.variantId(), line.quantity());
            }
            if (changed != 1) {
                throw new IllegalStateException("Inventory transition failed");
            }
        }
        int changed = jdbc.update("""
            UPDATE app.reserva SET estado = ?, ultimo_evento_id = ? WHERE id = ? AND estado = ?
            """, state, eventId, reservation.id(), reservation.state());
        if (changed != 1) {
            throw new IllegalStateException("Reservation transition failed");
        }

        switch (state) {
            case "LIBERADA" -> result(reservation, eventId, ReservationMessages.RELEASED, now,
                new ReleasedData(reservation.id(), reason));
            case "EXPIRADA" -> result(reservation, eventId, ReservationMessages.EXPIRED, now,
                new ExpiredData(reservation.id(), reservation.expiresAt()));
            case "CONSUMIDA" -> result(reservation, eventId, ReservationMessages.CONSUMED, now,
                new ConsumedData(reservation.id()));
            default -> throw new IllegalStateException("Unsupported reservation transition");
        }
    }

    private Instant now() {
        return jdbc.queryForObject("SELECT clock_timestamp()", (row, index) -> row.getTimestamp(1).toInstant());
    }

    private void result(Reservation reservation, UUID id, String type, Instant now, Object data) {
        var message = new ResultMessage(id, type, reservation.orderId(), now, data);
        jdbc.update("""
            INSERT INTO app.outbox_catalogo(id, exchange, routing_key, cuerpo)
            VALUES (?, 'catalog.events', ?, CAST(? AS jsonb))
            """, id, type, json.writeValueAsString(message));
    }

    private Reservation reservation(java.sql.ResultSet row) throws java.sql.SQLException {
        return new Reservation(row.getObject("id", UUID.class), row.getObject("order_id", UUID.class),
            row.getString("estado"), row.getTimestamp("expira_en").toInstant(),
            row.getObject("payment_id", UUID.class), row.getObject("ultimo_evento_id", UUID.class));
    }

    private record Reservation(UUID id, UUID orderId, String state, Instant expiresAt,
                               UUID paymentId, UUID lastEvent) {
    }

    private record Line(UUID variantId, int quantity) {
    }
}
