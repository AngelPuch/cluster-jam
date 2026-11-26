package com.clusterjam.catalog.infrastructure.messaging;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.UUID;

import com.clusterjam.catalog.application.outbox.OutboxEvent;
import com.clusterjam.catalog.application.outbox.OutboxPublicationFailure;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.ReturnedMessage;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

class RabbitMqCatalogEventPublisherTest {

    @Test
    void publishesPersistentJsonWithTheOriginalIdentity() {
        var template = new ReplyTemplate("ACK");
        OutboxEvent event = event();
        new RabbitMqCatalogEventPublisher(template).publish(event);
        assertEquals(event.exchange(), template.exchange);
        assertEquals(event.type(), template.routingKey);
        var properties = template.sent.getMessageProperties();
        assertEquals(event.messageId().toString(), properties.getMessageId());
        assertEquals(event.orderId().toString(), properties.getCorrelationId());
        assertEquals(event.type(), properties.getType());
        assertEquals("application/json", properties.getContentType());
        assertEquals("UTF-8", properties.getContentEncoding());
        assertEquals(MessageDeliveryMode.PERSISTENT, properties.getDeliveryMode());
        assertArrayEquals(event.body().getBytes(StandardCharsets.UTF_8), template.sent.getBody());
    }

    @Test
    void rejectsNacksReturnsAndMissingConfirms() {
        for (String reply : List.of("NACK", "RETURN", "TIMEOUT")) {
            OutboxEvent event = event();
            var publisher = new RabbitMqCatalogEventPublisher(new ReplyTemplate(reply));
            var failure = assertThrows(OutboxPublicationFailure.class, () -> publisher.publish(event));
            assertEquals(event.messageId(), failure.messageId());
            assertEquals(switch (reply) {
                case "NACK" -> "BROKER_NACK";
                case "RETURN" -> "EVENT_UNROUTABLE";
                default -> "CONFIRM_UNAVAILABLE";
            }, failure.getMessage());
        }
    }

    private OutboxEvent event() {
        UUID id = UUID.randomUUID();
        UUID order = UUID.randomUUID();
        String type = "catalog.inventory.reservation-rejected.v1";
        String body = """
            {"messageId":"%s","type":"%s","orderId":"%s","occurredAt":"2026-11-25T18:00:00Z",
             "data":{"reason":"OUT_OF_STOCK"}}
            """.formatted(id, type, order);
        return new OutboxEvent(id, order, "catalog.events", type, body);
    }

    private static class ReplyTemplate extends RabbitTemplate {

        private final String reply;
        private Message sent;
        private String exchange;
        private String routingKey;

        ReplyTemplate(String reply) {
            this.reply = reply;
        }

        @Override
        public void send(String exchange, String routingKey, Message message, CorrelationData correlation) {
            this.sent = message;
            this.exchange = exchange;
            this.routingKey = routingKey;
            if (reply.equals("RETURN")) {
                correlation.setReturned(new ReturnedMessage(message, 312, "NO_ROUTE", exchange, routingKey));
            }
            if (!reply.equals("TIMEOUT")) {
                correlation.getFuture().complete(new CorrelationData.Confirm(!reply.equals("NACK"), null));
            }
        }
    }
}
