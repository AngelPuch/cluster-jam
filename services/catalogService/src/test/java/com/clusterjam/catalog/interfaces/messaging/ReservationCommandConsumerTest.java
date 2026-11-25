package com.clusterjam.catalog.interfaces.messaging;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import com.clusterjam.catalog.application.reservations.ReservationMessages.ReserveCommand;
import com.clusterjam.catalog.application.reservations.ReservationService;
import com.rabbitmq.client.Channel;
import jakarta.validation.Validation;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import tools.jackson.databind.json.JsonMapper;

class ReservationCommandConsumerTest {

    @Test
    void acknowledgesAfterTheServiceReturnsAndRejectsInvalidMessages() throws Exception {
        try (var factory = Validation.buildDefaultValidatorFactory()) {
            var returned = new AtomicBoolean();
            var calls = new AtomicInteger();
            var acks = new AtomicInteger();
            var rejects = new AtomicInteger();
            var service = new ReservationService(command -> { }) {
                @Override
                public void reserve(ReserveCommand command) {
                    calls.incrementAndGet();
                    returned.set(true);
                }
            };
            var reader = new ReservationMessageReader(new JsonMapper(), factory.getValidator());
            var consumer = new ReservationCommandConsumer(reader, service);
            Channel channel = channel(returned, acks, rejects);
            consumer.receive(message(false), channel);
            assertEquals(1, calls.get());
            assertEquals(1, acks.get());
            consumer.receive(message(true), channel);
            assertEquals(1, calls.get());
            assertEquals(1, acks.get());
            assertEquals(1, rejects.get());
        }
    }

    @Test
    void retriesTechnicalFailuresThreeTimesThenRejectsWithoutRequeue() throws Exception {
        try (var factory = Validation.buildDefaultValidatorFactory()) {
            var calls = new AtomicInteger();
            var acks = new AtomicInteger();
            var rejects = new AtomicInteger();
            var service = new ReservationService(command -> { }) {
                @Override
                public void reserve(ReserveCommand command) {
                    calls.incrementAndGet();
                    throw new IllegalStateException("Fixture database failure");
                }
            };
            var reader = new ReservationMessageReader(new JsonMapper(), factory.getValidator());
            new ReservationCommandConsumer(reader, service)
                .receive(message(false), channel(new AtomicBoolean(), acks, rejects));
            assertEquals(3, calls.get());
            assertEquals(0, acks.get());
            assertEquals(1, rejects.get());
        }
    }

    private Channel channel(AtomicBoolean returned, AtomicInteger acks, AtomicInteger rejects) {
        return (Channel) Proxy.newProxyInstance(Channel.class.getClassLoader(), new Class<?>[] {Channel.class},
            (proxy, method, arguments) -> {
                if (method.getName().equals("basicAck")) {
                    assertTrue(returned.get());
                    acks.incrementAndGet();
                }
                if (method.getName().equals("basicReject")) {
                    assertFalse((Boolean) arguments[1]);
                    rejects.incrementAndGet();
                }
                return null;
            });
    }

    private Message message(boolean invalid) {
        String id = "00000000-0000-4000-8000-000000000003";
        String order = "00000000-0000-4000-8000-000000000001";
        var properties = new MessageProperties();
        properties.setDeliveryTag(1);
        properties.setReceivedExchange("catalog.commands");
        properties.setReceivedRoutingKey("cmd.catalog.reserve-stock.v1");
        properties.setMessageId(id);
        properties.setCorrelationId(order);
        properties.setType("cmd.catalog.reserve-stock.v1");
        String body = invalid ? "{}" : """
            {"messageId":"%s","type":"cmd.catalog.reserve-stock.v1","orderId":"%s",
             "occurredAt":"2026-11-25T18:00:00Z","data":{"quoteValidUntil":"2026-11-25T18:05:00Z",
             "lines":[{"variantId":"00000000-0000-4000-8000-000000000004",
             "quantity":2,"expectedBasePriceCents":19900}]}}
            """.formatted(id, order);
        return new Message(body.getBytes(java.nio.charset.StandardCharsets.UTF_8), properties);
    }
}
