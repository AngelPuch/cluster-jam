package com.clusterjam.catalog.interfaces.messaging;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import com.clusterjam.catalog.application.reservations.ReservationMessages;
import com.clusterjam.catalog.application.reservations.ReservationMessages.Command;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ConfirmCommand;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ConfirmData;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ConsumeCommand;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ConsumeData;
import com.rabbitmq.client.AMQP;
import com.rabbitmq.client.ConnectionFactory;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.amqp.rabbit.listener.SimpleMessageListenerContainer;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcOperations;
import tools.jackson.databind.json.JsonMapper;

@EnabledIfEnvironmentVariable(named = "CATALOG_VERIFY_RABBITMQ", matches = "true")
@SpringBootTest(properties = {
    "catalog.messaging.enabled=true",
    "catalog.reservations.expiration-enabled=false",
    "catalog.outbox.enabled=false",
    "catalog.environment=test",
    "catalog.security.supabase-url=https://catalog-test.supabase.co",
    "catalog.reads.cursor-key=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    "spring.jpa.hibernate.ddl-auto=validate"
})
class ReservationRabbitTest {

    @Autowired
    private JdbcOperations jdbc;
    @Autowired
    private SimpleMessageListenerContainer reservationCommandsContainer;

    @Test
    void recoversQueuedCommandsAndCompletesTheLifecycleWithoutRepeatingStock() throws Exception {
        String host = System.getenv().getOrDefault("CATALOG_RABBITMQ_HOST", "127.0.0.1");
        assertEquals("127.0.0.1", host, "This smoke test is restricted to the loopback development broker");
        String password = System.getenv("CATALOG_TEST_ORDERS_PASSWORD");
        assertNotNull(password, "Set CATALOG_TEST_ORDERS_PASSWORD during the local smoke test");
        UUID variant = ReservationStockTest.fixture(5);
        var command = ReservationStockTest.command(UUID.randomUUID(), List.of(variant), 2);
        var factory = new ConnectionFactory();
        factory.setHost(host);
        factory.setPort(Integer.parseInt(System.getenv().getOrDefault("CATALOG_RABBITMQ_PORT", "5672")));
        factory.setVirtualHost(System.getenv().getOrDefault("CATALOG_RABBITMQ_VHOST", "clusterjam"));
        factory.setUsername("orders-test-publisher");
        factory.setPassword(password);
        factory.setConnectionTimeout(3000);
        reservationCommandsContainer.stop();
        try (var connection = factory.newConnection(); var channel = connection.createChannel()) {
            channel.confirmSelect();
            var properties = new AMQP.BasicProperties.Builder().contentType("application/json")
                .deliveryMode(2).messageId(command.messageId().toString()).type(command.type())
                .correlationId(command.orderId().toString()).build();
            byte[] body = new JsonMapper().writeValueAsBytes(command);
            channel.basicPublish("catalog.commands", command.type(), true, properties, body);
            channel.basicPublish("catalog.commands", command.type(), true, properties, body);
            channel.waitForConfirmsOrDie(5000);
            assertEquals(0, inboxCount(command.messageId()));
        } finally {
            reservationCommandsContainer.start();
        }
        Instant deadline = Instant.now().plusSeconds(10);
        while (Instant.now().isBefore(deadline) && inboxCount(command.messageId()) == 0) {
            Thread.sleep(100);
        }
        assertEquals(1, inboxCount(command.messageId()));
        assertEquals(2, jdbc.queryForObject("SELECT stock_reservado FROM app.inventario WHERE variante_id = ?",
            Integer.class, variant));
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM app.reserva WHERE order_id = ?",
            Integer.class, command.orderId()));
        assertTrue(jdbc.queryForObject("""
            SELECT EXISTS(SELECT 1 FROM app.inbox_catalogo i JOIN app.outbox_catalogo o ON o.id = i.resultado_id
                WHERE i.message_id = ? AND o.estado = 'PENDING' AND o.routing_key = ?)
            """, Boolean.class, command.messageId(), ReservationMessages.CREATED));

        UUID reservation = jdbc.queryForObject("SELECT id FROM app.reserva WHERE order_id = ?",
            UUID.class, command.orderId());
        try (var connection = factory.newConnection(); var channel = connection.createChannel()) {
            channel.confirmSelect();
            var confirm = new ConfirmCommand(UUID.randomUUID(), ReservationMessages.CONFIRM, command.orderId(),
                Instant.now(), new ConfirmData(reservation, UUID.randomUUID()));
            publishTwice(channel, confirm);
            awaitState(reservation, "CONFIRMADA");
            var consume = new ConsumeCommand(UUID.randomUUID(), ReservationMessages.CONSUME, command.orderId(),
                Instant.now(), new ConsumeData(reservation));
            publishTwice(channel, consume);
            awaitState(reservation, "CONSUMIDA");
        }
        assertEquals(3, jdbc.queryForObject("SELECT stock_fisico FROM app.inventario WHERE variante_id = ?",
            Integer.class, variant));
        assertEquals(0, jdbc.queryForObject("SELECT stock_reservado FROM app.inventario WHERE variante_id = ?",
            Integer.class, variant));

    }

    private void publishTwice(com.rabbitmq.client.Channel channel, Command command) throws Exception {
        var properties = new AMQP.BasicProperties.Builder().contentType("application/json")
            .deliveryMode(2).messageId(command.messageId().toString()).type(command.type())
            .correlationId(command.orderId().toString()).build();
        byte[] body = new JsonMapper().writeValueAsBytes(command);
        channel.basicPublish("catalog.commands", command.type(), true, properties, body);
        channel.basicPublish("catalog.commands", command.type(), true, properties, body);
        channel.waitForConfirmsOrDie(5000);
    }

    private void awaitState(UUID reservation, String expected) throws InterruptedException {
        Instant deadline = Instant.now().plusSeconds(10);
        while (Instant.now().isBefore(deadline)) {
            String state = jdbc.queryForObject("SELECT estado FROM app.reserva WHERE id = ?",
                String.class, reservation);
            if (expected.equals(state)) {
                return;
            }
            Thread.sleep(100);
        }
        assertEquals(expected, jdbc.queryForObject("SELECT estado FROM app.reserva WHERE id = ?",
            String.class, reservation));
    }

    private int inboxCount(UUID id) {
        return jdbc.queryForObject("SELECT count(*) FROM app.inbox_catalogo WHERE consumidor = ? AND message_id = ?",
            Integer.class, ReservationMessages.RESERVE, id);
    }
}
