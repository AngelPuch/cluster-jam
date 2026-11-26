package com.clusterjam.catalog.interfaces.messaging;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.net.ServerSocket;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.UUID;

import com.clusterjam.catalog.application.outbox.OutboxEvent;
import com.clusterjam.catalog.application.outbox.OutboxPublicationFailure;
import com.clusterjam.catalog.application.outbox.OutboxPublicationService;
import com.clusterjam.catalog.application.ports.OutboxStore;
import com.clusterjam.catalog.infrastructure.messaging.RabbitMqCatalogEventPublisher;
import com.rabbitmq.client.Channel;
import com.rabbitmq.client.ConnectionFactory;
import com.rabbitmq.client.GetResponse;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import tools.jackson.databind.json.JsonMapper;

@EnabledIfEnvironmentVariable(named = "CATALOG_VERIFY_RABBITMQ", matches = "true")
@SpringBootTest(properties = {
    "catalog.messaging.enabled=false",
    "catalog.outbox.enabled=false",
    "catalog.reservations.expiration-enabled=false",
    "catalog.environment=test",
    "catalog.security.supabase-url=https://catalog-test.supabase.co",
    "catalog.reads.cursor-key=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    "spring.jpa.hibernate.ddl-auto=validate"
})
class OutboxRabbitTest {

    @Autowired
    private OutboxPublicationService publications;
    @Autowired
    private OutboxStore store;
    @Autowired
    private JdbcOperations jdbc;
    @Autowired
    private PlatformTransactionManager transactionManager;

    @Test
    void publishesPersistentEventsAndRetriesAnUnroutableEventAfterBindingIsFixed() throws Exception {
        try (var holder = CatalogOutboxTestSupport.lockExistingPending();
             var connection = observer().newConnection(); var channel = connection.createChannel()) {
            String queue = temporaryQueue(channel);
            OutboxEvent valid = CatalogOutboxTestSupport.insert("catalog.inventory.reservation-rejected.v1");
            try {
                channel.queueBind(queue, "catalog.events", valid.type());
                assertEquals(valid.messageId(), publications.publishNext().orElseThrow());
                assertDelivery(channel, queue, valid);
                CatalogOutboxTestSupport.assertState(jdbc, valid.messageId(), "PUBLISHED");
            } finally {
                CatalogOutboxTestSupport.remove(valid.messageId());
            }

            OutboxEvent unroutable = CatalogOutboxTestSupport.insert("test.catalog.unroutable." + UUID.randomUUID());
            try {
                var failure = assertThrows(OutboxPublicationFailure.class, () -> publications.publishNext());
                assertEquals("EVENT_UNROUTABLE", failure.getMessage());
                CatalogOutboxTestSupport.assertState(jdbc, unroutable.messageId(), "PENDING");
                channel.queueBind(queue, "catalog.events", unroutable.type());
                assertEquals(unroutable.messageId(), publications.publishNext().orElseThrow());
                assertDelivery(channel, queue, unroutable);
                CatalogOutboxTestSupport.assertState(jdbc, unroutable.messageId(), "PUBLISHED");
            } finally {
                CatalogOutboxTestSupport.remove(unroutable.messageId());
            }
            holder.rollback();
        }
    }

    @Test
    void keepsPendingWhenConnectionFailsAndPublishesTheSameEventOnRecovery() throws Exception {
        try (var holder = CatalogOutboxTestSupport.lockExistingPending();
             var connection = observer().newConnection(); var channel = connection.createChannel()) {
            String queue = temporaryQueue(channel);
            OutboxEvent event = CatalogOutboxTestSupport.insert("catalog.inventory.reservation-rejected.v1");
            channel.queueBind(queue, "catalog.events", event.type());
            int closedPort;
            try (var probe = new ServerSocket(0, 1, java.net.InetAddress.getByName("127.0.0.1"))) {
                closedPort = probe.getLocalPort();
            }
            var unavailable = new CachingConnectionFactory("127.0.0.1", closedPort);
            unavailable.setConnectionTimeout(300);
            unavailable.setPublisherConfirmType(CachingConnectionFactory.ConfirmType.CORRELATED);
            unavailable.setPublisherReturns(true);
            try {
                var template = new RabbitTemplate(unavailable);
                template.setMandatory(true);
                var disconnected = new OutboxPublicationService(store, new RabbitMqCatalogEventPublisher(template));
                assertThrows(OutboxPublicationFailure.class,
                    () -> new TransactionTemplate(transactionManager).execute(status -> disconnected.publishNext()));
                CatalogOutboxTestSupport.assertState(jdbc, event.messageId(), "PENDING");
                assertEquals(event.messageId(), publications.publishNext().orElseThrow());
                assertDelivery(channel, queue, event);
                CatalogOutboxTestSupport.assertState(jdbc, event.messageId(), "PUBLISHED");
            } finally {
                unavailable.destroy();
                CatalogOutboxTestSupport.remove(event.messageId());
            }
            holder.rollback();
        }
    }

    private ConnectionFactory observer() {
        String host = System.getenv().getOrDefault("CATALOG_RABBITMQ_HOST", "127.0.0.1");
        assertEquals("127.0.0.1", host, "Run this test only against the loopback development broker");
        String password = System.getenv("CATALOG_TEST_OUTBOX_PASSWORD");
        assertNotNull(password, "Set CATALOG_TEST_OUTBOX_PASSWORD");
        var factory = new ConnectionFactory();
        factory.setHost(host);
        factory.setPort(Integer.parseInt(System.getenv().getOrDefault("CATALOG_RABBITMQ_PORT", "5672")));
        factory.setVirtualHost(System.getenv().getOrDefault("CATALOG_RABBITMQ_VHOST", "clusterjam"));
        factory.setUsername("catalog-publisher-test");
        factory.setPassword(password);
        factory.setConnectionTimeout(3000);
        return factory;
    }

    private String temporaryQueue(Channel channel) throws Exception {
        String queue = "catalog.publisher.test." + UUID.randomUUID();
        channel.queueDeclare(queue, false, true, true, null);
        return queue;
    }

    private void assertDelivery(Channel channel, String queue, OutboxEvent expected) throws Exception {
        Instant deadline = Instant.now().plusSeconds(5);
        GetResponse delivered;
        do {
            delivered = channel.basicGet(queue, true);
            if (delivered == null) {
                Thread.sleep(50);
            }
        } while (delivered == null && Instant.now().isBefore(deadline));
        assertNotNull(delivered, "Expected event in the temporary observer queue");
        var properties = delivered.getProps();
        assertEquals(expected.messageId().toString(), properties.getMessageId());
        assertEquals(expected.orderId().toString(), properties.getCorrelationId());
        assertEquals(expected.type(), properties.getType());
        assertEquals(Integer.valueOf(2), properties.getDeliveryMode());
        assertEquals("application/json", properties.getContentType());
        var json = new JsonMapper();
        assertEquals(json.readTree(expected.body()),
            json.readTree(new String(delivered.getBody(), StandardCharsets.UTF_8)));
    }
}
