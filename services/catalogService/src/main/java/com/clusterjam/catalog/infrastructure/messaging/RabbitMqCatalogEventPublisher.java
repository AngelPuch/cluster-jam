package com.clusterjam.catalog.infrastructure.messaging;

import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import com.clusterjam.catalog.application.outbox.OutboxEvent;
import com.clusterjam.catalog.application.outbox.OutboxPublicationFailure;
import com.clusterjam.catalog.application.ports.CatalogEventPublisher;
import org.springframework.amqp.AmqpException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Component;

@Component
public class RabbitMqCatalogEventPublisher implements CatalogEventPublisher {

    private final RabbitTemplate rabbit;

    public RabbitMqCatalogEventPublisher(RabbitTemplate rabbit) {
        this.rabbit = rabbit;
    }

    @Override
    public void publish(OutboxEvent event) {
        var properties = new MessageProperties();
        properties.setContentType(MessageProperties.CONTENT_TYPE_JSON);
        properties.setContentEncoding(StandardCharsets.UTF_8.name());
        properties.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
        properties.setMessageId(event.messageId().toString());
        properties.setCorrelationId(event.orderId().toString());
        properties.setType(event.type());
        var message = new Message(event.body().getBytes(StandardCharsets.UTF_8), properties);
        var correlation = new CorrelationData();
        try {
            rabbit.send(event.exchange(), event.type(), message, correlation);
            var confirm = correlation.getFuture().get(3, TimeUnit.SECONDS);
            if (!confirm.ack()) {
                throw new OutboxPublicationFailure(event.messageId(), "BROKER_NACK");
            }
            if (correlation.getReturned() != null) {
                throw new OutboxPublicationFailure(event.messageId(), "EVENT_UNROUTABLE");
            }
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new OutboxPublicationFailure(event.messageId(), "PUBLICATION_INTERRUPTED");
        } catch (TimeoutException | ExecutionException unavailable) {
            throw new OutboxPublicationFailure(event.messageId(), "CONFIRM_UNAVAILABLE");
        } catch (AmqpException unavailable) {
            throw new OutboxPublicationFailure(event.messageId(), "BROKER_UNAVAILABLE");
        }
    }
}
