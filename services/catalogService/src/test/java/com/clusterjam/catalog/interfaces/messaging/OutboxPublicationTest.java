package com.clusterjam.catalog.interfaces.messaging;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

import com.clusterjam.catalog.application.outbox.OutboxEvent;
import com.clusterjam.catalog.application.outbox.OutboxPublicationFailure;
import com.clusterjam.catalog.application.outbox.OutboxPublicationService;
import com.clusterjam.catalog.application.ports.CatalogEventPublisher;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@EnabledIfEnvironmentVariable(named = "CATALOG_VERIFY_POSTGRES", matches = "true")
@SpringBootTest(properties = {
    "catalog.messaging.enabled=false",
    "catalog.outbox.enabled=false",
    "catalog.reservations.expiration-enabled=false",
    "catalog.environment=test",
    "catalog.security.supabase-url=https://catalog-test.supabase.co",
    "catalog.reads.cursor-key=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    "spring.jpa.hibernate.ddl-auto=validate"
})
class OutboxPublicationTest {

    @Autowired
    private OutboxPublicationService publications;
    @Autowired
    private ProbePublisher probe;
    @Autowired
    private JdbcOperations jdbc;

    @Test
    void retainsTheSqlLockUntilPublicationAndRetriesWithTheSameIdAfterFailure() throws Exception {
        try (var holder = CatalogOutboxTestSupport.lockExistingPending()) {
            OutboxEvent event = CatalogOutboxTestSupport.insert("catalog.inventory.reservation-rejected.v1");
            try {
                probe.fail = true;
                probe.seen.clear();
                assertThrows(OutboxPublicationFailure.class, () -> publications.publishNext());
                CatalogOutboxTestSupport.assertState(jdbc, event.messageId(), "PENDING");
                probe.fail = false;
                assertEquals(event.messageId(), publications.publishNext().orElseThrow());
                CatalogOutboxTestSupport.assertState(jdbc, event.messageId(), "PUBLISHED");
                assertEquals(2, probe.seen.size());
                assertEquals(probe.seen.getFirst(), probe.seen.getLast());
                assertTrue(publications.publishNext().isEmpty());
            } finally {
                CatalogOutboxTestSupport.remove(event.messageId());
            }
            holder.rollback();
        }
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class FixtureConfiguration {

        @Bean
        @Primary
        ProbePublisher probePublisher() {
            return new ProbePublisher();
        }
    }

    static class ProbePublisher implements CatalogEventPublisher {

        private boolean fail;
        private final List<OutboxEvent> seen = new ArrayList<>();

        @Override
        public void publish(OutboxEvent event) {
            assertTrue(TransactionSynchronizationManager.isActualTransactionActive());
            // Another real PostgreSQL session must be unable to acquire this same row.
            try (var connection = ReservationStockTest.admin().getDataSource().getConnection();
                 var statement = connection.prepareStatement(
                     "SELECT id FROM app.outbox_catalogo WHERE id = ? FOR UPDATE NOWAIT")) {
                statement.setObject(1, event.messageId());
                SQLException blocked = assertThrows(SQLException.class, statement::executeQuery);
                assertEquals("55P03", blocked.getSQLState());
                try (var foreignKeyRead = connection.prepareStatement(
                    "SELECT id FROM app.outbox_catalogo WHERE id = ? FOR KEY SHARE NOWAIT")) {
                    foreignKeyRead.setObject(1, event.messageId());
                    try (var rows = foreignKeyRead.executeQuery()) {
                        assertTrue(rows.next());
                    }
                }
            } catch (SQLException fixtureFailure) {
                throw new IllegalStateException(fixtureFailure);
            }
            seen.add(event);
            if (fail) {
                throw new OutboxPublicationFailure(event.messageId(), "FIXTURE_CONFIRMATION_LOST_AFTER_SEND");
            }
        }
    }
}
