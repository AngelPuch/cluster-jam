package com.clusterjam.catalog.application.inventory;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public final class InventoryModels {

    private InventoryModels() {
    }

    public record Balance(UUID variantId, int physicalQuantity, int reservedQuantity,
                          int availableQuantity, int version) {
    }

    public record Adjustment(UUID variantId, int quantityDelta, String reason) {
    }

    public record Movement(UUID id, UUID variantId, String type, int quantityDelta, String reason,
                           UUID actorRef, int physicalBefore, int physicalAfter, int reservedQuantity,
                           int availableQuantity, int inventoryVersion, Instant createdAt) {
    }

    public record Result(Movement movement, boolean replayed) {
    }

    public record History(List<Movement> items, Integer nextAfterVersion) {
    }
}
