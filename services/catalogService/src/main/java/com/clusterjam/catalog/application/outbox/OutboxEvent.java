package com.clusterjam.catalog.application.outbox;

import java.util.UUID;

public record OutboxEvent(UUID messageId, UUID orderId, String exchange, String type, String body) {
}
