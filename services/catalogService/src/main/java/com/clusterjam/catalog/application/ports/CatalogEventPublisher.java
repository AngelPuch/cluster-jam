package com.clusterjam.catalog.application.ports;

import com.clusterjam.catalog.application.outbox.OutboxEvent;

public interface CatalogEventPublisher {

    void publish(OutboxEvent event);
}
