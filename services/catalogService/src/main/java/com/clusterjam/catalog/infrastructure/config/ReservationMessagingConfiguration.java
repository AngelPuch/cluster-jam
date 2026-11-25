package com.clusterjam.catalog.infrastructure.config;

import com.clusterjam.catalog.application.reservations.ReservationService;
import com.clusterjam.catalog.interfaces.messaging.ReservationCommandConsumer;
import com.clusterjam.catalog.interfaces.messaging.ReservationMessageReader;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.listener.SimpleMessageListenerContainer;
import org.springframework.amqp.rabbit.listener.api.ChannelAwareMessageListener;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "catalog.messaging.enabled", havingValue = "true")
public class ReservationMessagingConfiguration {

    @Bean
    SimpleMessageListenerContainer reservationCommandsContainer(
        ConnectionFactory connectionFactory, ReservationMessageReader reader, ReservationService service
    ) {
        var container = new SimpleMessageListenerContainer(connectionFactory);
        container.setQueueNames("catalog.commands.v1");
        container.setAcknowledgeMode(AcknowledgeMode.MANUAL);
        container.setConcurrentConsumers(1);
        container.setPrefetchCount(1);
        container.setDeBatchingEnabled(false);
        container.setAutoDeclare(false);
        container.setMissingQueuesFatal(true);
        container.setRecoveryInterval(5000L);
        container.setErrorHandler(error -> LoggerFactory.getLogger(ReservationMessagingConfiguration.class)
            .warn("catalog_reservation_delivery_failed"));
        var consumer = new ReservationCommandConsumer(reader, service);
        container.setMessageListener((ChannelAwareMessageListener) consumer::receive);
        return container;
    }
}
