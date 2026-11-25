package com.clusterjam.catalog.interfaces.messaging;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import com.clusterjam.catalog.application.reservations.ReservationMessages;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ReserveCommand;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ReserveData;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ReserveLine;
import com.clusterjam.catalog.application.reservations.ReservationService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

@EnabledIfEnvironmentVariable(named = "CATALOG_VERIFY_POSTGRES", matches = "true")
@SpringBootTest(properties = {
    "catalog.messaging.enabled=false",
    "catalog.environment=test",
    "catalog.security.supabase-url=https://catalog-test.supabase.co",
    "catalog.reads.cursor-key=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    "spring.jpa.hibernate.ddl-auto=validate"
})
class ReservationStockTest {

    @Autowired
    private ReservationService service;
    @Autowired
    private JdbcOperations jdbc;

    private final JsonMapper json = new JsonMapper();

    @Test
    void reservesOncePerMessageAndOrderAndKeepsTheOriginalExpiry() {
        UUID variant = fixture(5);
        ReserveCommand command = command(UUID.randomUUID(), List.of(variant), 2);
        service.reserve(command);
        JsonNode first = outcome(command.orderId());
        service.reserve(command);
        service.reserve(new ReserveCommand(UUID.randomUUID(), command.type(), command.orderId(),
            command.occurredAt(), command.data()));
        assertEquals(first, outcome(command.orderId()));
        assertEquals(2, reserved(variant));
        assertEquals(5, number("SELECT stock_fisico FROM app.inventario WHERE variante_id = ?", variant));
        assertEquals(1, number("SELECT count(*) FROM app.reserva WHERE order_id = ?", command.orderId()));
        assertEquals(1, number("SELECT count(*) FROM app.inbox_catalogo WHERE order_id = ?", command.orderId()));
        Instant created = Instant.parse(first.get("occurredAt").asString());
        Instant expires = Instant.parse(first.get("data").get("expiresAt").asString());
        assertEquals(Duration.ofMinutes(15), Duration.between(created, expires));
        assertEquals(ReservationMessages.CREATED, first.get("type").asString());
        assertEquals("PENDING", jdbc.queryForObject("""
            SELECT estado FROM app.outbox_catalogo WHERE id = ?
            """, String.class, UUID.fromString(first.get("messageId").asString())));
    }

    @Test
    void rejectsTheWholeBasketAndDoesNotReopenARejectedOrder() {
        UUID available = fixture(5);
        UUID empty = fixture(0);
        ReserveCommand command = command(UUID.randomUUID(), List.of(available, empty), 2);
        service.reserve(command);
        JsonNode rejected = outcome(command.orderId());
        assertEquals(ReservationMessages.REJECTED, rejected.get("type").asString());
        assertEquals("OUT_OF_STOCK", rejected.get("data").get("reason").asString());
        assertEquals(0, reserved(available));
        assertEquals(0, reserved(empty));
        assertEquals(0, number("SELECT count(*) FROM app.reserva WHERE order_id = ?", command.orderId()));
        admin().update("UPDATE app.inventario SET stock_fisico = 5, version = version + 1 WHERE variante_id = ?",
            empty);
        service.reserve(new ReserveCommand(UUID.randomUUID(), command.type(), command.orderId(),
            command.occurredAt(), command.data()));
        assertEquals(rejected, outcome(command.orderId()));
        assertEquals(0, reserved(available));
        assertEquals(0, number("SELECT count(*) FROM app.reserva WHERE order_id = ?", command.orderId()));
    }

    @Test
    void serializesTwoBuyersForTheLastUnit() throws Exception {
        UUID variant = fixture(1);
        ReserveCommand left = command(UUID.randomUUID(), List.of(variant), 1);
        ReserveCommand right = command(UUID.randomUUID(), List.of(variant), 1);
        var start = new CountDownLatch(1);
        var one = CompletableFuture.runAsync(() -> reserveAfter(start, left));
        var two = CompletableFuture.runAsync(() -> reserveAfter(start, right));
        start.countDown();
        CompletableFuture.allOf(one, two).get(15, TimeUnit.SECONDS);
        var types = List.of(outcome(left.orderId()).get("type").asString(),
            outcome(right.orderId()).get("type").asString()).stream().sorted().toList();
        assertEquals(List.of(ReservationMessages.CREATED, ReservationMessages.REJECTED), types);
        assertEquals(1, reserved(variant));
        assertEquals(1, number("SELECT stock_fisico FROM app.inventario WHERE variante_id = ?", variant));
        assertTrue(jdbc.queryForObject("""
            SELECT bool_and(stock_reservado >= 0 AND stock_reservado <= stock_fisico) FROM app.inventario
            """, Boolean.class));
    }

    private void reserveAfter(CountDownLatch start, ReserveCommand command) {
        try {
            start.await();
            service.reserve(command);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(interrupted);
        }
    }

    static ReserveCommand command(UUID order, List<UUID> variants, int quantity) {
        return new ReserveCommand(UUID.randomUUID(), ReservationMessages.RESERVE, order, Instant.now(),
            new ReserveData(Instant.now().plusSeconds(300),
                variants.stream().map(id -> new ReserveLine(id, quantity, 19900L)).toList()));
    }

    static UUID fixture(int physical) {
        UUID product = UUID.randomUUID();
        UUID variant = UUID.randomUUID();
        var admin = admin();
        admin.update("""
            INSERT INTO app.producto(id,tipo_prenda_id,nombre,estado) VALUES (?,1,'Reservation test','PUBLICADO')
            """, product);
        admin.update("""
            INSERT INTO app.variante(id,producto_id,talla_id,color_id,sku,precio_base_centavos,estado)
            VALUES (?,?,1,1,?,19900,'PUBLICADO')
            """, variant, product, variant.toString().toUpperCase(java.util.Locale.ROOT));
        admin.update("INSERT INTO app.inventario(variante_id,stock_fisico) VALUES (?,?)", variant, physical);
        return variant;
    }

    static JdbcTemplate admin() {
        return new JdbcTemplate(new DriverManagerDataSource(System.getenv("CATALOG_DB_URL"),
            "migrator_catalogo", System.getenv("CATALOG_MIGRATION_PASSWORD")));
    }

    private int reserved(UUID variant) {
        return number("SELECT stock_reservado FROM app.inventario WHERE variante_id = ?", variant);
    }

    private int number(String sql, Object parameter) {
        return jdbc.queryForObject(sql, Integer.class, parameter);
    }

    private JsonNode outcome(UUID order) {
        return json.readTree(jdbc.queryForObject("""
            SELECT o.cuerpo::text FROM app.inbox_catalogo i
            JOIN app.outbox_catalogo o ON o.id = i.resultado_id
            WHERE i.consumidor = ? AND i.order_id = ?
            """, String.class, ReservationMessages.RESERVE, order));
    }
}
