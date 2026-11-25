package com.clusterjam.catalog.interfaces.messaging;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import com.clusterjam.catalog.application.reservations.InvalidReservationMessage;
import com.clusterjam.catalog.application.reservations.ReservationLifecycleService;
import com.clusterjam.catalog.application.reservations.ReservationMessages;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ConfirmCommand;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ConfirmData;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ConsumeCommand;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ConsumeData;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ReleaseCommand;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ReleaseData;
import com.clusterjam.catalog.application.reservations.ReservationService;
import com.clusterjam.catalog.interfaces.workers.ReservationExpirationWorker;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@EnabledIfEnvironmentVariable(named = "CATALOG_VERIFY_POSTGRES", matches = "true")
@SpringBootTest(properties = {
    "catalog.messaging.enabled=false",
    "catalog.reservations.expiration-enabled=false",
    "catalog.environment=test",
    "catalog.security.supabase-url=https://catalog-test.supabase.co",
    "catalog.reads.cursor-key=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    "spring.jpa.hibernate.ddl-auto=validate"
})
class ReservationLifecycleTest {

    @Autowired
    private ReservationService reservations;
    @Autowired
    private ReservationLifecycleService lifecycle;
    @Autowired
    private JdbcOperations jdbc;
    @Autowired
    private PlatformTransactionManager transactionManager;

    @Test
    void confirmationRetainsStockAndProductionConsumesItOnlyOnce() {
        Purchase purchase = purchase();
        var confirm = confirm(purchase);
        int version = inventory(purchase, "version");
        lifecycle.transition(confirm);
        assertEquals("CONFIRMADA", state(purchase));
        assertEquals(5, inventory(purchase, "stock_fisico"));
        assertEquals(2, inventory(purchase, "stock_reservado"));
        assertEquals(version, inventory(purchase, "version"));
        lifecycle.transition(confirm);
        lifecycle.transition(confirm(purchase));
        assertEquals(1, events(purchase, ReservationMessages.CONFIRMED));

        expireDate(purchase, Instant.now().minusSeconds(1));
        new ReservationExpirationWorker(lifecycle).expire();
        assertEquals("CONFIRMADA", state(purchase));
        var consume = consume(purchase);
        lifecycle.transition(consume);
        lifecycle.transition(consume);
        lifecycle.transition(consume(purchase));
        assertEquals("CONSUMIDA", state(purchase));
        assertEquals(3, inventory(purchase, "stock_fisico"));
        assertEquals(0, inventory(purchase, "stock_reservado"));
        assertEquals(version + 1, inventory(purchase, "version"));
        assertEquals(1, events(purchase, ReservationMessages.CONSUMED));
        assertEquals(0, events(purchase, ReservationMessages.EXPIRED));
    }

    @Test
    void releasingActiveOrConfirmedReservationsDoesNotRepeatTheDelta() {
        for (boolean confirmed : List.of(false, true)) {
            Purchase purchase = purchase();
            if (confirmed) {
                lifecycle.transition(confirm(purchase));
            }
            var release = release(purchase);
            lifecycle.transition(release);
            lifecycle.transition(release);
            lifecycle.transition(release(purchase));
            assertEquals("LIBERADA", state(purchase));
            assertEquals(5, inventory(purchase, "stock_fisico"));
            assertEquals(0, inventory(purchase, "stock_reservado"));
            assertEquals(1, events(purchase, ReservationMessages.RELEASED));
            lifecycle.transition(confirm(purchase));
            assertEquals("LIBERADA", state(purchase));
            assertEquals(confirmed ? 1 : 0, events(purchase, ReservationMessages.CONFIRMED));
        }
    }

    @Test
    void lateConfirmationExpiresImmediatelyAndTheJobAlsoExpiresWithoutDuplicates() {
        Purchase late = purchase();
        expireDate(late, Instant.now().minusSeconds(1));
        lifecycle.transition(confirm(late));
        lifecycle.transition(confirm(late));
        lifecycle.transition(release(late));
        assertExpired(late);
        assertEquals(0, events(late, ReservationMessages.RELEASED));
        assertEquals(0, events(late, ReservationMessages.CONFIRMED));
        UUID expirationEvent = jdbc.queryForObject("SELECT ultimo_evento_id FROM app.reserva WHERE id = ?",
            UUID.class, late.reservation());
        assertEquals(expirationEvent, jdbc.queryForObject("""
            SELECT resultado_id FROM app.inbox_catalogo WHERE consumidor = ? AND order_id = ?
            """, UUID.class, ReservationMessages.RELEASE, late.order()));

        Purchase abandoned = purchase();
        // Make this fixture the oldest due row without changing any other reservation.
        expireDate(abandoned, Instant.now().minusSeconds(365L * 24 * 60 * 60));
        var worker = new ReservationExpirationWorker(lifecycle);
        worker.expire();
        worker.expire();
        assertExpired(abandoned);
    }

    @Test
    void confirmationUsesDatabaseWallTimeAfterWaitingForTheReservationLock() throws Exception {
        Purchase purchase = purchase();
        var started = new CountDownLatch(1);
        CompletableFuture<Void> pending;
        try (var holder = ReservationStockTest.admin().getDataSource().getConnection()) {
            holder.setAutoCommit(false);
            try (var statement = holder.prepareStatement("SELECT id FROM app.reserva WHERE id = ? FOR UPDATE")) {
                statement.setObject(1, purchase.reservation());
                statement.executeQuery().close();
            }
            pending = CompletableFuture.runAsync(() -> new TransactionTemplate(transactionManager)
                .executeWithoutResult(status -> {
                    jdbc.execute("SET LOCAL lock_timeout = '4s'");
                    jdbc.execute("SET LOCAL statement_timeout = '5s'");
                    jdbc.queryForObject("SELECT current_timestamp", Timestamp.class);
                    started.countDown();
                    lifecycle.transition(confirm(purchase));
                }));
            assertTrue(started.await(3, TimeUnit.SECONDS));
            try (var statement = holder.prepareStatement("""
                UPDATE app.reserva SET creado_en = clock_timestamp() - interval '20 minutes',
                    expira_en = clock_timestamp() + interval '400 milliseconds' WHERE id = ?
                """)) {
                statement.setObject(1, purchase.reservation());
                statement.executeUpdate();
            }
            Thread.sleep(650);
            assertFalse(pending.isDone());
            holder.commit();
        }
        pending.get(10, TimeUnit.SECONDS);
        assertExpired(purchase);
        assertEquals(0, events(purchase, ReservationMessages.CONFIRMED));
    }

    @Test
    void wrongIdentityAndProductionBeforeConfirmationCannotModifyStock() {
        Purchase purchase = purchase();
        var wrongOrder = new ConfirmCommand(UUID.randomUUID(), ReservationMessages.CONFIRM, UUID.randomUUID(),
            Instant.now(), new ConfirmData(purchase.reservation(), purchase.payment()));
        assertThrows(InvalidReservationMessage.class, () -> lifecycle.transition(wrongOrder));
        assertThrows(InvalidReservationMessage.class, () -> lifecycle.transition(consume(purchase)));
        assertEquals("ACTIVA", state(purchase));
        assertEquals(2, inventory(purchase, "stock_reservado"));
        assertEquals(5, inventory(purchase, "stock_fisico"));
        assertEquals(0, jdbc.queryForObject("""
            SELECT count(*) FROM app.inbox_catalogo WHERE order_id = ? AND consumidor <> ?
            """, Integer.class, purchase.order(), ReservationMessages.RESERVE));
        lifecycle.transition(confirm(purchase));
        var wrongPayment = new ConfirmCommand(UUID.randomUUID(), ReservationMessages.CONFIRM, purchase.order(),
            Instant.now(), new ConfirmData(purchase.reservation(), UUID.randomUUID()));
        assertThrows(InvalidReservationMessage.class, () -> lifecycle.transition(wrongPayment));
        assertEquals(1, events(purchase, ReservationMessages.CONFIRMED));
    }

    private Purchase purchase() {
        UUID variant = ReservationStockTest.fixture(5);
        UUID order = UUID.randomUUID();
        reservations.reserve(ReservationStockTest.command(order, List.of(variant), 2));
        UUID reservation = jdbc.queryForObject("SELECT id FROM app.reserva WHERE order_id = ?", UUID.class, order);
        return new Purchase(order, reservation, variant, UUID.randomUUID());
    }

    private ConfirmCommand confirm(Purchase purchase) {
        return new ConfirmCommand(UUID.randomUUID(), ReservationMessages.CONFIRM, purchase.order(), Instant.now(),
            new ConfirmData(purchase.reservation(), purchase.payment()));
    }

    private ReleaseCommand release(Purchase purchase) {
        return new ReleaseCommand(UUID.randomUUID(), ReservationMessages.RELEASE, purchase.order(), Instant.now(),
            new ReleaseData(purchase.reservation(), "Customer cancellation"));
    }

    private ConsumeCommand consume(Purchase purchase) {
        return new ConsumeCommand(UUID.randomUUID(), ReservationMessages.CONSUME, purchase.order(), Instant.now(),
            new ConsumeData(purchase.reservation()));
    }

    private void expireDate(Purchase purchase, Instant expires) {
        ReservationStockTest.admin().update("""
            UPDATE app.reserva SET creado_en = ?, expira_en = ? WHERE id = ?
            """, Timestamp.from(expires.minusSeconds(900)), Timestamp.from(expires), purchase.reservation());
    }

    private String state(Purchase purchase) {
        return jdbc.queryForObject("SELECT estado FROM app.reserva WHERE id = ?", String.class, purchase.reservation());
    }

    private int inventory(Purchase purchase, String column) {
        if (!List.of("stock_fisico", "stock_reservado", "version").contains(column)) {
            throw new IllegalArgumentException("Unsupported fixture column");
        }
        return jdbc.queryForObject("SELECT " + column + " FROM app.inventario WHERE variante_id = ?",
            Integer.class, purchase.variant());
    }

    private int events(Purchase purchase, String type) {
        return jdbc.queryForObject("SELECT count(*) FROM app.outbox_catalogo WHERE cuerpo->>'orderId' = ? "
            + "AND routing_key = ?", Integer.class, purchase.order().toString(), type);
    }

    private void assertExpired(Purchase purchase) {
        assertEquals("EXPIRADA", state(purchase));
        assertEquals(0, inventory(purchase, "stock_reservado"));
        assertEquals(5, inventory(purchase, "stock_fisico"));
        assertEquals(1, events(purchase, ReservationMessages.EXPIRED));
    }

    private record Purchase(UUID order, UUID reservation, UUID variant, UUID payment) {
    }
}
