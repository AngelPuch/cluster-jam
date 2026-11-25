package com.clusterjam.catalog.interfaces.messaging;

import java.io.IOException;

import com.clusterjam.catalog.application.reservations.InvalidReservationMessage;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ReserveCommand;
import com.clusterjam.catalog.application.reservations.ReservationService;
import com.rabbitmq.client.Channel;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.core.Message;

public final class ReservationCommandConsumer {

    private static final Logger LOG = LoggerFactory.getLogger(ReservationCommandConsumer.class);
    private final ReservationMessageReader reader;
    private final ReservationService service;

    public ReservationCommandConsumer(ReservationMessageReader reader, ReservationService service) {
        this.reader = reader;
        this.service = service;
    }

    public void receive(Message message, Channel channel) throws IOException {
        var properties = message.getMessageProperties();
        long tag = properties.getDeliveryTag();
        ReserveCommand command;
        try {
            command = reader.read(message.getBody(), properties.getReceivedRoutingKey());
            if (!"catalog.commands".equals(properties.getReceivedExchange())
                || !command.messageId().toString().equalsIgnoreCase(properties.getMessageId())
                || !command.orderId().toString().equalsIgnoreCase(properties.getCorrelationId())
                || !command.type().equals(properties.getType())) {
                throw new InvalidReservationMessage();
            }
        } catch (InvalidReservationMessage invalid) {
            LOG.warn("catalog_reservation_invalid_message");
            channel.basicReject(tag, false);
            return;
        }

        for (int attempt = 1; attempt <= 3; attempt++) {
            try {
                service.reserve(command);
                break;
            } catch (RuntimeException technical) {
                if (attempt == 3) {
                    LOG.atWarn().addKeyValue("message_id", command.messageId())
                        .addKeyValue("order_id", command.orderId()).log("catalog_reservation_retries_exhausted");
                    channel.basicReject(tag, false);
                    return;
                }
                try {
                    Thread.sleep(1000);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new IOException("Reservation delivery interrupted", interrupted);
                }
            }
        }
        // Spring's transactional service proxy has committed before this call returns.
        channel.basicAck(tag, false);
        LOG.atInfo().addKeyValue("message_id", command.messageId())
            .addKeyValue("order_id", command.orderId()).log("catalog_reservation_committed");
    }
}
